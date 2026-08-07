from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from stm32cubemx_mcp.cubemx import ScriptRunner, run_cubemx_script, validate_ioc_content
from stm32cubemx_mcp.ioc import (
    IocDocument,
    encode_ioc_text,
    get_project_toolchain_key,
    load_ioc_document,
)
from stm32cubemx_mcp.models import (
    Diagnostic,
    IocValidationResult,
    ProjectGenerationRequest,
    ProjectGenerationResult,
)
from stm32cubemx_mcp.settings import Settings

ContentValidator = Callable[[Path, bytes, Settings], IocValidationResult]
_PARENT_PROJECT_URI = re.compile(r"^PARENT-(\d+)-PROJECT_LOC(?:/(.*))?$")


def _quoted(path: Path) -> str:
    value = str(path)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(f"CubeMX project path has invalid characters: {path}")
    return f'"{value}"'


def build_generation_script(
    ioc_path: Path,
    project_path: Path,
    project_name: str,
) -> list[str]:
    """Build the commands for one STM32CubeIDE project generation."""
    return [
        f"config load {_quoted(ioc_path)}",
        f"project name {project_name}",
        "project toolchain STM32CubeIDE",
        f"project path {_quoted(project_path)}",
        "project generate",
        "exit",
    ]


def _project_root(stage: Path) -> Path | None:
    candidates = {
        project_file.parent
        for project_file in stage.rglob(".project")
        if (project_file.parent / ".cproject").is_file()
    }
    if len(candidates) != 1:
        return None
    return candidates.pop()


def _prepare_staged_ioc(
    source: bytes,
    document: IocDocument,
    request: ProjectGenerationRequest,
) -> bytes:
    updates: OrderedDict[str, str] = OrderedDict(
        [
            ("ProjectManager.ProjectName", request.project_name),
            ("ProjectManager.ProjectFileName", f"{request.project_name}.ioc"),
            (get_project_toolchain_key(document.entries), request.toolchain),
            ("ProjectManager.UnderRoot", "true"),
        ]
    )
    return encode_ioc_text(document.render(updates), source)


def _resolve_link_target(project_root: Path, container: Path, location_uri: str) -> Path | None:
    if location_uri == "PROJECT_LOC":
        target = project_root
    elif location_uri.startswith("PROJECT_LOC/"):
        target = project_root / location_uri.removeprefix("PROJECT_LOC/")
    else:
        match = _PARENT_PROJECT_URI.fullmatch(location_uri)
        if match is None:
            return None
        target = project_root
        for _ in range(int(match.group(1))):
            target = target.parent
        if match.group(2):
            target = target / match.group(2)
    resolved = target.resolve(strict=False)
    if not resolved.is_relative_to(container.resolve()):
        return None
    return resolved


def validate_generated_project(
    container: Path,
    project_root: Path,
    project_name: str,
) -> list[Diagnostic]:
    """Validate CubeIDE metadata, linked resources, identity, and required files."""
    diagnostics: list[Diagnostic] = []
    project_file = project_root / ".project"
    cproject_file = project_root / ".cproject"
    if not project_file.is_file() or not cproject_file.is_file():
        return [
            Diagnostic(
                severity="error",
                code="generation.project_metadata_missing",
                message="The generated project does not contain .project and .cproject files.",
            )
        ]

    try:
        project_xml = ET.parse(project_file)
    except ET.ParseError as error:
        return [
            Diagnostic(
                severity="error",
                code="generation.project_metadata_invalid",
                message=f"The generated .project file is not valid XML: {error}",
            )
        ]
    eclipse_name = project_xml.findtext("./name")
    if eclipse_name != project_name:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="generation.project_name_mismatch",
                message=(
                    f"The Eclipse project name is {eclipse_name!r}. "
                    f"The requested name is {project_name!r}."
                ),
            )
        )

    for link in project_xml.findall("./linkedResources/link"):
        name = link.findtext("name") or "<unnamed>"
        location_uri = link.findtext("locationURI")
        if not location_uri:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="generation.linked_resource_invalid",
                    message=f"Linked resource {name!r} does not have a location URI.",
                )
            )
            continue
        target = _resolve_link_target(project_root, container, location_uri)
        if target is None:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="generation.linked_resource_unsafe",
                    message=f"Linked resource {name!r} has an unsupported location: {location_uri}",
                )
            )
        elif not target.exists():
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="generation.linked_resource_missing",
                    message=f"Linked resource {name!r} does not exist at {location_uri}.",
                )
            )

    files = [path for path in container.rglob("*") if path.is_file()]
    expected = {
        "main.c": any(path.name.lower() == "main.c" for path in files),
        "main.h": any(path.name.lower() == "main.h" for path in files),
        "a CMSIS core header": any(
            path.name.lower().startswith("core_cm") and path.suffix.lower() == ".h"
            for path in files
        ),
        "a HAL source file": any(
            re.fullmatch(r"stm32.*_hal\.c", path.name.lower()) for path in files
        ),
    }
    missing_expected = [name for name, exists in expected.items() if not exists]
    if missing_expected:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="generation.required_files_missing",
                message="The generated project is missing: " + ", ".join(missing_expected),
            )
        )

    ioc_name = f"{project_name}.ioc"
    matching_ioc = [path for path in files if path.name == ioc_name]
    if not matching_ioc:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="generation.ioc_missing",
                message=f"The generated project does not contain {ioc_name}.",
            )
        )
    else:
        document = IocDocument.parse(matching_ioc[0].read_text(encoding="utf-8-sig"))
        internal_name = document.entries.get("ProjectManager.ProjectName")
        internal_file = document.entries.get("ProjectManager.ProjectFileName")
        if internal_name != project_name or internal_file != ioc_name:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="generation.ioc_identity_mismatch",
                    message=(
                        "The generated IOC filename and internal project identity do not match "
                        f"{project_name!r}."
                    ),
                )
            )
    return diagnostics


def relocate_text_paths(project_root: Path, source_root: Path, destination: Path) -> None:
    text_names = {"CMakeLists.txt"}
    text_suffixes = {
        ".cproject",
        ".ioc",
        ".json",
        ".launch",
        ".mxproject",
        ".project",
        ".txt",
    }
    stage_forms = {str(source_root), source_root.as_posix()}
    destination_forms = {str(destination), destination.as_posix()}
    replacements = list(zip(sorted(stage_forms), sorted(destination_forms), strict=True))

    for path in project_root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
            continue
        if path.name not in text_names and path.suffix.lower() not in text_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relocated = text
        for source, target in replacements:
            relocated = relocated.replace(source, target)
        if relocated != text:
            path.write_text(relocated, encoding="utf-8")


def promote_directory(source: Path, destination: Path) -> None:
    """Move a staged directory and tolerate a completed Windows rename."""
    for attempt in range(12):
        try:
            source.replace(destination)
            return
        except PermissionError:
            if not source.exists() and destination.is_dir():
                return
            if attempt == 11:
                raise
            time.sleep(min(0.1 * (2**attempt), 0.5))


def _generated_files(project_path: Path, limit: int = 500) -> list[str]:
    files: list[str] = []
    for path in sorted(project_path.rglob("*"), key=lambda item: str(item).lower()):
        if path.is_file():
            files.append(path.relative_to(project_path).as_posix())
            if len(files) == limit:
                break
    return files


def generate_project(
    request: ProjectGenerationRequest,
    settings: Settings,
    *,
    validator: ContentValidator = validate_ioc_content,
    script_runner: ScriptRunner = run_cubemx_script,
) -> ProjectGenerationResult:
    """Generate one new STM32CubeIDE project from an IOC file."""
    source_path, source, source_document = load_ioc_document(request.ioc_path, settings)
    source_sha256 = hashlib.sha256(source).hexdigest()
    destination = settings.resolve_allowed_path(request.output_directory, must_exist=False)
    settings.resolve_allowed_path(destination.parent)
    if destination.exists():
        raise FileExistsError(f"Project output directory already exists: {destination}")

    stage = Path(
        tempfile.mkdtemp(prefix=f".{request.project_name}-cubemx-", dir=destination.parent)
    )
    promoted = False
    destination_owned = False
    try:
        staged_ioc = stage / f"{request.project_name}.ioc"
        staged_content = _prepare_staged_ioc(source, source_document, request)
        staged_ioc.write_bytes(staged_content)
        validation = validator(staged_ioc, staged_content, settings).model_copy(
            update={"path": str(destination / staged_ioc.name)}
        )
        common = {
            "output_directory": str(destination),
            "project_name": request.project_name,
            "toolchain": request.toolchain,
            "source_sha256": source_sha256,
            "validation": validation,
        }
        if not validation.valid:
            return ProjectGenerationResult(
                succeeded=False,
                project_path=str(destination),
                **common,
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        code="generation.ioc_invalid",
                        message="STM32CubeMX did not validate the staged IOC file.",
                    )
                ],
            )

        commands = build_generation_script(
            staged_ioc,
            stage,
            request.project_name,
        )
        process = script_runner(commands, settings, stage)
        if not process.succeeded:
            return ProjectGenerationResult(
                succeeded=False,
                project_path=str(destination),
                **common,
                cubemx=process,
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        code="generation.cubemx_failed",
                        message="STM32CubeMX did not complete project generation.",
                    )
                ],
            )

        project_root = _project_root(stage)
        if project_root is None:
            return ProjectGenerationResult(
                succeeded=False,
                project_path=str(destination),
                **common,
                cubemx=process,
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        code="generation.artifacts_missing",
                        message="CubeMX did not create one CubeIDE project root.",
                    )
                ],
            )

        if not any(stage.rglob(staged_ioc.name)):
            (project_root / staged_ioc.name).write_bytes(staged_content)
        artifact_diagnostics = validate_generated_project(stage, project_root, request.project_name)
        if any(item.severity == "error" for item in artifact_diagnostics):
            return ProjectGenerationResult(
                succeeded=False,
                project_path=str(destination),
                **common,
                cubemx=process,
                diagnostics=artifact_diagnostics,
            )

        project_relative = project_root.relative_to(stage)
        relocate_text_paths(stage, stage, destination)
        promote_directory(stage, destination)
        destination_owned = True
        final_project_root = destination / project_relative
        final_diagnostics = validate_generated_project(
            destination, final_project_root, request.project_name
        )
        if any(item.severity == "error" for item in final_diagnostics):
            shutil.rmtree(destination, ignore_errors=True)
            destination_owned = False
            return ProjectGenerationResult(
                succeeded=False,
                project_path=str(destination),
                **common,
                cubemx=process,
                diagnostics=final_diagnostics,
            )
        promoted = True
        return ProjectGenerationResult(
            succeeded=True,
            **common,
            project_path=str(final_project_root),
            cubemx=process,
            generated_files=_generated_files(destination),
        )
    finally:
        if not promoted or stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if destination_owned and not promoted and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
