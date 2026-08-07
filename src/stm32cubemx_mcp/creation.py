from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from stm32cubemx_mcp.cubemx import (
    ScriptRunner,
    compact_process_result,
    run_cubemx_script,
    successful_process_diagnostics,
    validate_ioc_content,
)
from stm32cubemx_mcp.generation import relocate_text_paths
from stm32cubemx_mcp.models import (
    Diagnostic,
    IocCreateRequest,
    IocCreateResult,
    IocValidationResult,
)
from stm32cubemx_mcp.settings import Settings

ContentValidator = Callable[[Path, bytes, Settings], IocValidationResult]


def _quoted(path: Path) -> str:
    value = str(path)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(f"CubeMX IOC path has invalid characters: {path}")
    return f'"{value}"'


def build_ioc_creation_script(
    request: IocCreateRequest,
    project_path: Path,
    ioc_path: Path,
) -> list[str]:
    """Build typed commands that create one IOC file."""
    if request.target_kind == "board":
        load_command = f"loadboard {request.target} {request.board_mode}"
    else:
        load_command = f"load {request.target}"
    return [
        load_command,
        f"project name {request.project_name}",
        f"project toolchain {request.toolchain}",
        f"project path {_quoted(project_path)}",
        f"config saveas {_quoted(ioc_path)}",
        "exit",
    ]


def _remove_stage(stage: Path) -> None:
    deadline = time.monotonic() + 10.0
    while stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
        if not stage.exists() or time.monotonic() >= deadline:
            return
        time.sleep(0.1)


def _destination_has_expected_ioc(
    destination: Path,
    destination_ioc: Path,
    source_sha256: str,
) -> bool:
    if not destination.is_dir():
        return False
    entries = list(destination.iterdir())
    if entries != [destination_ioc] or not destination_ioc.is_file():
        raise FileExistsError(
            f"CubeMX created unexpected content in the IOC output directory: {destination}"
        )
    destination_sha256 = hashlib.sha256(destination_ioc.read_bytes()).hexdigest()
    if destination_sha256 != source_sha256:
        raise OSError("The CubeMX-created IOC hash does not match the validated IOC hash.")
    return True


def create_ioc(
    request: IocCreateRequest,
    settings: Settings,
    *,
    validator: ContentValidator = validate_ioc_content,
    script_runner: ScriptRunner = run_cubemx_script,
) -> IocCreateResult:
    """Create and validate one IOC file in a new output directory."""
    destination = settings.resolve_allowed_path(request.output_directory, must_exist=False)
    settings.resolve_allowed_path(destination.parent)
    if destination.exists():
        raise FileExistsError(f"IOC output directory already exists: {destination}")

    destination_ioc = destination / f"{request.project_name}.ioc"
    stage = Path(tempfile.mkdtemp(prefix=f".{request.project_name}-ioc-", dir=destination.parent))
    promoted = False
    destination_created = False
    try:
        staged_ioc = stage / destination_ioc.name
        commands = build_ioc_creation_script(request, stage, staged_ioc)
        process = script_runner(commands, settings, stage)
        process_diagnostics = successful_process_diagnostics(process)
        common = {
            "ioc_path": str(destination_ioc),
            "project_path": str(destination),
            "project_name": request.project_name,
            "target_kind": request.target_kind,
            "target": request.target,
            "board_mode": request.board_mode if request.target_kind == "board" else None,
            "toolchain": request.toolchain,
            "cubemx": compact_process_result(process),
        }
        if not process.succeeded:
            return IocCreateResult(
                succeeded=False,
                **common,
                diagnostics=[
                    *process_diagnostics,
                    Diagnostic(
                        severity="error",
                        code="creation.cubemx_failed",
                        message="STM32CubeMX did not complete IOC creation.",
                    ),
                ],
            )
        if not staged_ioc.is_file():
            return IocCreateResult(
                succeeded=False,
                **common,
                diagnostics=[
                    *process_diagnostics,
                    Diagnostic(
                        severity="error",
                        code="creation.ioc_missing",
                        message="STM32CubeMX did not create the IOC file.",
                    ),
                ],
            )

        relocate_text_paths(stage, stage, destination)
        content = staged_ioc.read_bytes()
        source_sha256 = hashlib.sha256(content).hexdigest()
        validation = validator(staged_ioc, content, settings).model_copy(
            update={"path": str(destination_ioc)}
        )
        if not validation.valid:
            if _destination_has_expected_ioc(destination, destination_ioc, source_sha256):
                destination_created = True
            return IocCreateResult(
                succeeded=False,
                **common,
                source_sha256=source_sha256,
                validation=validation,
                diagnostics=[
                    *process_diagnostics,
                    Diagnostic(
                        severity="error",
                        code="creation.ioc_invalid",
                        message="STM32CubeMX did not validate the new IOC file.",
                    ),
                ],
            )

        if _destination_has_expected_ioc(destination, destination_ioc, source_sha256):
            destination_created = True
        else:
            destination.mkdir()
            destination_created = True
            shutil.copy2(staged_ioc, destination_ioc)
            copied_sha256 = hashlib.sha256(destination_ioc.read_bytes()).hexdigest()
            if copied_sha256 != source_sha256:
                raise OSError("The copied IOC hash does not match the validated IOC hash.")
        promoted = True
        return IocCreateResult(
            succeeded=True,
            **common,
            source_sha256=source_sha256,
            validation=validation,
            diagnostics=process_diagnostics,
        )
    finally:
        _remove_stage(stage)
        if not promoted and destination_created and destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
