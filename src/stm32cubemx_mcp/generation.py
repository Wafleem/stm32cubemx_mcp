from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from stm32cubemx_mcp.cubemx import ScriptRunner, run_cubemx_script, validate_ioc_content
from stm32cubemx_mcp.ioc import load_ioc_document
from stm32cubemx_mcp.models import (
    Diagnostic,
    IocValidationResult,
    ProjectGenerationRequest,
    ProjectGenerationResult,
)
from stm32cubemx_mcp.settings import Settings

ContentValidator = Callable[[Path, bytes, Settings], IocValidationResult]


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
    source_path, source, _ = load_ioc_document(request.ioc_path, settings)
    source_sha256 = hashlib.sha256(source).hexdigest()
    destination = settings.resolve_allowed_path(request.output_directory, must_exist=False)
    settings.resolve_allowed_path(destination.parent)
    if destination.exists():
        raise FileExistsError(f"Project output directory already exists: {destination}")

    validation = validator(source_path, source, settings)
    if not validation.valid:
        return ProjectGenerationResult(
            succeeded=False,
            project_path=str(destination),
            project_name=request.project_name,
            toolchain=request.toolchain,
            source_sha256=source_sha256,
            validation=validation,
            diagnostics=[
                Diagnostic(
                    severity="error",
                    code="generation.ioc_invalid",
                    message="STM32CubeMX did not validate the source IOC file.",
                )
            ],
        )

    stage = Path(
        tempfile.mkdtemp(prefix=f".{request.project_name}-cubemx-", dir=destination.parent)
    )
    promoted = False
    try:
        staged_ioc = stage / f"{request.project_name}.ioc"
        staged_ioc.write_bytes(source)
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
                project_name=request.project_name,
                toolchain=request.toolchain,
                source_sha256=source_sha256,
                validation=validation,
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
                project_name=request.project_name,
                toolchain=request.toolchain,
                source_sha256=source_sha256,
                validation=validation,
                cubemx=process,
                diagnostics=[
                    Diagnostic(
                        severity="error",
                        code="generation.artifacts_missing",
                        message="CubeMX did not create one CubeIDE project root.",
                    )
                ],
            )

        if not any(project_root.glob("*.ioc")):
            shutil.copy2(staged_ioc, project_root / staged_ioc.name)
        relocate_text_paths(project_root, stage, destination)
        if project_root == stage:
            stage.replace(destination)
        else:
            project_root.replace(destination)
        promoted = True
        return ProjectGenerationResult(
            succeeded=True,
            project_path=str(destination),
            project_name=request.project_name,
            toolchain=request.toolchain,
            source_sha256=source_sha256,
            validation=validation,
            cubemx=process,
            generated_files=_generated_files(destination),
        )
    finally:
        if not promoted or stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
