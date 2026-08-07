from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from stm32cubemx_mcp.cubemx import ScriptRunner, run_cubemx_script, validate_ioc_content
from stm32cubemx_mcp.generation import (
    ContentValidator,
    build_generation_script,
    relocate_text_paths,
)
from stm32cubemx_mcp.ioc import get_project_toolchain, load_ioc_document
from stm32cubemx_mcp.models import (
    CubeMXProcessResult,
    Diagnostic,
    IocValidationResult,
    ProjectFileChange,
    RegenerationPlanRequest,
    RegenerationPlanResult,
)
from stm32cubemx_mcp.settings import Settings

_IGNORED_DIRECTORIES = {".git", ".venv", "Debug", "Release", "build", "dist"}
_TEXT_NAMES = {"CMakeLists.txt", "Makefile"}
_TEXT_SUFFIXES = {
    ".c",
    ".cmake",
    ".cproject",
    ".h",
    ".ioc",
    ".json",
    ".launch",
    ".ld",
    ".md",
    ".mxproject",
    ".project",
    ".s",
    ".txt",
    ".xml",
}
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class FileState:
    sha256: str
    size: int


def _ignored_directory(name: str) -> bool:
    return name in _IGNORED_DIRECTORIES or name.startswith("cmake-build-")


def _is_reparse_point(path: Path) -> bool:
    file_attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(file_attributes & reparse_flag)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_project(root: Path, settings: Settings) -> dict[str, FileState]:
    """Create a bounded content manifest for one project directory."""
    manifest: dict[str, FileState] = {}
    total_size = 0
    for directory_name, child_directories, file_names in os.walk(root, followlinks=False):
        directory = Path(directory_name)
        kept_directories: list[str] = []
        for name in child_directories:
            child = directory / name
            if _ignored_directory(name):
                continue
            if child.is_symlink() or _is_reparse_point(child):
                raise ValueError(f"Project directory contains a link or reparse point: {child}")
            kept_directories.append(name)
        child_directories[:] = kept_directories

        for name in file_names:
            path = directory / name
            if path.is_symlink() or _is_reparse_point(path):
                raise ValueError(f"Project file is a link or reparse point: {path}")
            if not path.is_file():
                raise ValueError(f"Project contains an unsupported file type: {path}")
            size = path.stat().st_size
            total_size += size
            if len(manifest) + 1 > settings.max_project_files:
                raise ValueError("Project file count exceeds CUBEMX_MCP_MAX_PROJECT_FILES")
            if total_size > settings.max_project_bytes:
                raise ValueError("Project size exceeds CUBEMX_MCP_MAX_PROJECT_BYTES")
            relative = path.relative_to(root).as_posix()
            manifest[relative] = FileState(sha256=_file_sha256(path), size=size)
    return manifest


def _manifest_sha256(manifest: dict[str, FileState]) -> str:
    data = [
        {"path": path, "sha256": state.sha256, "size": state.size}
        for path, state in sorted(manifest.items())
    ]
    return hashlib.sha256(
        json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    del directory
    return {name for name in names if _ignored_directory(name)}


def _text_diff(
    before_path: Path | None,
    after_path: Path | None,
    relative_path: str,
    limit: int = 128 * 1024,
) -> str | None:
    sample_path = before_path or after_path
    if sample_path is None:
        return None
    if sample_path.name not in _TEXT_NAMES and sample_path.suffix.lower() not in _TEXT_SUFFIXES:
        return None
    if before_path is not None and before_path.stat().st_size > limit:
        return None
    if after_path is not None and after_path.stat().st_size > limit:
        return None
    try:
        before = before_path.read_text(encoding="utf-8").splitlines() if before_path else []
        after = after_path.read_text(encoding="utf-8").splitlines() if after_path else []
    except UnicodeDecodeError:
        return None
    return "\n".join(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
    )


def _project_changes(
    original_root: Path,
    staged_root: Path,
    before: dict[str, FileState],
    after: dict[str, FileState],
) -> list[ProjectFileChange]:
    changes: list[ProjectFileChange] = []
    for relative in sorted(before.keys() | after.keys()):
        before_state = before.get(relative)
        after_state = after.get(relative)
        if before_state == after_state:
            continue
        if before_state is None:
            change = "added"
        elif after_state is None:
            change = "deleted"
        else:
            change = "modified"
        before_path = original_root / relative if before_state else None
        after_path = staged_root / relative if after_state else None
        changes.append(
            ProjectFileChange(
                path=relative,
                change=change,
                before_sha256=before_state.sha256 if before_state else None,
                after_sha256=after_state.sha256 if after_state else None,
                before_size=before_state.size if before_state else None,
                after_size=after_state.size if after_state else None,
                unified_diff=_text_diff(before_path, after_path, relative),
            )
        )
    return changes


def _manifest_change_description(before: dict[str, FileState], after: dict[str, FileState]) -> str:
    added = sorted(after.keys() - before.keys())
    deleted = sorted(before.keys() - after.keys())
    modified = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
    parts: list[str] = []
    if added:
        parts.append("Added: " + ", ".join(added))
    if modified:
        parts.append("Modified: " + ", ".join(modified))
    if deleted:
        parts.append("Deleted: " + ", ".join(deleted))
    return "; ".join(parts) or "No changed path was identified."


def _failed_plan(
    *,
    project: Path,
    ioc_path: Path,
    source_manifest_sha256: str,
    code: str,
    message: str,
    validation: IocValidationResult | None = None,
    process: CubeMXProcessResult | None = None,
) -> RegenerationPlanResult:
    return RegenerationPlanResult(
        succeeded=False,
        project_path=str(project),
        ioc_path=str(ioc_path),
        source_manifest_sha256=source_manifest_sha256,
        changes=[],
        validation=validation,
        cubemx=process,
        diagnostics=[Diagnostic(severity="error", code=code, message=message)],
    )


def _select_ioc(
    request: RegenerationPlanRequest,
    project: Path,
    manifest: dict[str, FileState],
    settings: Settings,
) -> Path:
    if request.ioc_path:
        requested = Path(request.ioc_path)
        if not requested.is_absolute():
            requested = project / requested
        ioc_path = settings.resolve_allowed_path(requested)
        if not ioc_path.is_relative_to(project):
            raise ValueError("The IOC file is outside the project directory")
        if ioc_path.suffix.lower() != ".ioc":
            raise ValueError(f"Expected an IOC file: {ioc_path}")
        return ioc_path

    candidates = [project / path for path in manifest if Path(path).suffix.lower() == ".ioc"]
    if len(candidates) != 1:
        raise ValueError("The project must contain one IOC file or specify ioc_path")
    return candidates[0]


def plan_project_regeneration(
    request: RegenerationPlanRequest,
    settings: Settings,
    *,
    validator: ContentValidator = validate_ioc_content,
    script_runner: ScriptRunner = run_cubemx_script,
) -> RegenerationPlanResult:
    """Regenerate a staged project copy and return a read-only file plan."""
    project = settings.resolve_allowed_path(request.project_directory)
    if not project.is_dir():
        raise ValueError(f"Project path is not a directory: {project}")
    if not (project / ".project").is_file() or not (project / ".cproject").is_file():
        raise ValueError("The directory is not an STM32CubeIDE project")

    before = snapshot_project(project, settings)
    before_sha256 = _manifest_sha256(before)
    ioc_path = _select_ioc(request, project, before, settings)
    _, ioc_content, ioc_document = load_ioc_document(ioc_path, settings)
    toolchain = get_project_toolchain(ioc_document.entries)
    if toolchain not in {None, "STM32CubeIDE"}:
        raise ValueError(f"The IOC toolchain is not STM32CubeIDE: {toolchain}")
    project_name = ioc_document.entries.get("ProjectManager.ProjectName") or project.name
    if not _PROJECT_NAME.fullmatch(project_name):
        raise ValueError(f"The CubeMX project name is invalid: {project_name}")

    with tempfile.TemporaryDirectory(
        prefix=f".{project.name}-regeneration-", dir=project.parent
    ) as container_name:
        container = Path(container_name)
        stage = container / "project"
        current_before_copy = snapshot_project(project, settings)
        if current_before_copy != before:
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code="regeneration.source_changed_before_copy",
                message=(
                    "The source project changed before the staged copy. "
                    + _manifest_change_description(before, current_before_copy)
                ),
            )
        shutil.copytree(
            project,
            stage,
            symlinks=True,
            copy_function=shutil.copy2,
            ignore=_copy_ignore,
        )
        copied = snapshot_project(stage, settings)
        if _manifest_sha256(copied) != before_sha256:
            current_after_copy = snapshot_project(project, settings)
            code = (
                "regeneration.source_changed_during_copy"
                if current_after_copy != before
                else "regeneration.copy_mismatch"
            )
            message = (
                "The source project changed during the staged copy. "
                + _manifest_change_description(before, current_after_copy)
                if current_after_copy != before
                else "The staged project copy does not match the source project manifest."
            )
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code=code,
                message=message,
            )

        validation_directory = container / "validation"
        validation_directory.mkdir()
        validation_ioc = validation_directory / ioc_path.name
        validation_ioc.write_bytes(ioc_content)
        validation = validator(validation_ioc, ioc_content, settings).model_copy(
            update={"path": str(ioc_path)}
        )
        current_after_validation = snapshot_project(project, settings)
        if current_after_validation != before:
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code="regeneration.source_changed_after_validation",
                message=(
                    "The source project changed after IOC validation. "
                    + _manifest_change_description(before, current_after_validation)
                ),
                validation=validation,
            )
        if not validation.valid:
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code="regeneration.ioc_invalid",
                message="STM32CubeMX did not validate the existing project IOC file.",
                validation=validation,
            )

        staged_ioc = stage / ioc_path.relative_to(project)
        commands = build_generation_script(staged_ioc, stage, project_name)
        process = script_runner(commands, settings, stage)
        if not process.succeeded:
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code="regeneration.cubemx_failed",
                message="STM32CubeMX did not complete staged project regeneration.",
                validation=validation,
                process=process,
            )
        if not (stage / ".project").is_file() or not (stage / ".cproject").is_file():
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code="regeneration.artifacts_missing",
                message="STM32CubeMX removed required CubeIDE project files.",
                validation=validation,
                process=process,
            )

        relocate_text_paths(stage, stage, project)
        after = snapshot_project(stage, settings)
        after_sha256 = _manifest_sha256(after)
        current = snapshot_project(project, settings)
        if current != before:
            return _failed_plan(
                project=project,
                ioc_path=ioc_path,
                source_manifest_sha256=before_sha256,
                code="regeneration.source_changed_during_preview",
                message=(
                    "The source project changed during regeneration preview. "
                    + _manifest_change_description(before, current)
                ),
                validation=validation,
                process=process,
            )
        changes = _project_changes(project, stage, before, after)

    plan_data = {
        "project": str(project),
        "ioc": str(ioc_path),
        "source": before_sha256,
        "planned": after_sha256,
    }
    plan_id = hashlib.sha256(
        json.dumps(plan_data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return RegenerationPlanResult(
        succeeded=True,
        plan_id=plan_id,
        project_path=str(project),
        ioc_path=str(ioc_path),
        source_manifest_sha256=before_sha256,
        planned_manifest_sha256=after_sha256,
        changes=changes,
        validation=validation,
        cubemx=process,
        diagnostics=[
            Diagnostic(
                severity="info",
                code="regeneration.preview_only",
                message="This regeneration plan did not change the source project.",
            )
        ],
    )
