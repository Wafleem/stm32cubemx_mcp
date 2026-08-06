from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from stm32cubemx_mcp.discovery import discover_environment
from stm32cubemx_mcp.ioc import IocDocument, load_ioc_document
from stm32cubemx_mcp.models import (
    CubeMXProcessResult,
    Diagnostic,
    ExecutableInfo,
    IocValidationResult,
)
from stm32cubemx_mcp.settings import Settings

_PIN_INDEX_KEY = re.compile(r"^Mcu\.Pin\d+$")
_IP_INDEX_KEY = re.compile(r"^Mcu\.IP\d+$")

ScriptRunner = Callable[[list[str], Settings, Path], CubeMXProcessResult]


def _script_path(path: Path) -> str:
    value = str(path)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(f"CubeMX script path has invalid characters: {path}")
    return f'"{value}"'


def build_validation_script(input_path: Path, output_path: Path) -> list[str]:
    """Build the CubeMX commands for an IOC load and save test."""
    return [
        f"config load {_script_path(input_path)}",
        f"project path {_script_path(output_path.parent)}",
        f"config saveas {_script_path(output_path)}",
        "exit",
    ]


def build_cubemx_command(executable: ExecutableInfo, script_path: Path) -> list[str]:
    """Build a quiet CubeMX command without a command shell."""
    if not executable.available or not executable.invocation_prefix:
        raise FileNotFoundError("STM32CubeMX is not available")
    return [*executable.invocation_prefix, "-q", str(script_path)]


def _limit_output(text: str | None, limit: int) -> str:
    value = text or ""
    if len(value) <= limit:
        return value
    removed = len(value) - limit
    head_size = limit // 4
    tail_size = limit - head_size
    return (
        f"{value[:head_size]}\n[Output truncated. Removed {removed} characters.]\n"
        f"{value[-tail_size:]}"
    )


def run_cubemx_script(
    commands: list[str],
    settings: Settings,
    work_directory: Path,
) -> CubeMXProcessResult:
    """Run typed CubeMX script commands in quiet mode."""
    if not commands or commands[-1].strip().lower() != "exit":
        raise ValueError("A CubeMX script must end with the exit command")
    if any("\n" in command or "\r" in command for command in commands):
        raise ValueError("A CubeMX script command cannot contain a line break")

    report = discover_environment(settings)
    if not report.cubemx:
        raise FileNotFoundError("STM32CubeMX was not found")
    executable = report.cubemx[0]
    script_path = work_directory / "commands.mxscript"
    script_path.write_text("\n".join(commands) + "\n", encoding="utf-8")
    command = build_cubemx_command(executable, script_path)
    start = time.monotonic()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        try:
            completed = subprocess.run(
                command,
                cwd=work_directory,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.cubemx_timeout_seconds,
                check=False,
                shell=False,
                creationflags=creation_flags,
            )
        except subprocess.TimeoutExpired as error:
            return CubeMXProcessResult(
                succeeded=False,
                timed_out=True,
                duration_seconds=time.monotonic() - start,
                stdout=_limit_output(error.stdout, settings.max_process_output_chars),
                stderr=_limit_output(error.stderr, settings.max_process_output_chars),
            )
    finally:
        script_path.unlink(missing_ok=True)

    return CubeMXProcessResult(
        succeeded=completed.returncode == 0,
        exit_code=completed.returncode,
        duration_seconds=time.monotonic() - start,
        stdout=_limit_output(completed.stdout, settings.max_process_output_chars),
        stderr=_limit_output(completed.stderr, settings.max_process_output_chars),
    )


def _default_required_entries(document: IocDocument) -> dict[str, str]:
    required: dict[str, str] = {}
    for key, value in document.entries.items():
        is_required = (
            key in {"Mcu.CPN", "Mcu.Name", "ProjectManager.ToolChain"}
            or _PIN_INDEX_KEY.fullmatch(key)
            or _IP_INDEX_KEY.fullmatch(key)
            or key.endswith((".Signal", ".GPIO_Label", ".Locked"))
        )
        if is_required:
            required[key] = value
    return required


def _compare_required_entries(
    required: Mapping[str, str], roundtrip: IocDocument
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    roundtrip_pins = {
        value for key, value in roundtrip.entries.items() if _PIN_INDEX_KEY.fullmatch(key)
    }
    roundtrip_peripherals = {
        value for key, value in roundtrip.entries.items() if _IP_INDEX_KEY.fullmatch(key)
    }

    for key, expected in required.items():
        if _PIN_INDEX_KEY.fullmatch(key):
            actual_matches = expected in roundtrip_pins
        elif _IP_INDEX_KEY.fullmatch(key):
            actual_matches = expected in roundtrip_peripherals
        elif key in {"Mcu.PinsNb", "Mcu.IPNb"}:
            continue
        else:
            actual_matches = roundtrip.entries.get(key) == expected
        if not actual_matches:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="ioc.roundtrip_mismatch",
                    message=f"CubeMX did not preserve the required IOC setting: {key}",
                )
            )
    return diagnostics


def validate_ioc_content(
    source_path: Path,
    content: bytes,
    settings: Settings,
    *,
    required_entries: Mapping[str, str] | None = None,
    script_runner: ScriptRunner = run_cubemx_script,
) -> IocValidationResult:
    """Validate IOC content with a CubeMX load and save test."""
    source_sha256 = hashlib.sha256(content).hexdigest()
    source_document = IocDocument.parse(content.decode("utf-8-sig"))
    requirements = dict(required_entries or _default_required_entries(source_document))
    diagnostics = list(source_document.diagnostics)

    with tempfile.TemporaryDirectory(
        prefix=f".{source_path.stem}-cubemx-", dir=source_path.parent
    ) as temporary_name:
        stage = Path(temporary_name)
        staged_input = stage / source_path.name
        roundtrip_path = stage / "roundtrip.ioc"
        staged_input.write_bytes(content)
        commands = build_validation_script(staged_input, roundtrip_path)
        process = script_runner(commands, settings, stage)

        if not process.succeeded:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="cubemx.process_failed",
                    message="STM32CubeMX did not complete the IOC validation script.",
                )
            )
            return IocValidationResult(
                path=str(source_path),
                valid=False,
                source_sha256=source_sha256,
                cubemx=process,
                diagnostics=diagnostics,
            )
        ok_responses = len(re.findall(r"(?m)^\s*OK\s*$", process.stdout))
        if ok_responses < 2:
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="cubemx.script_response_missing",
                    message="STM32CubeMX did not confirm both validation commands.",
                )
            )
            return IocValidationResult(
                path=str(source_path),
                valid=False,
                source_sha256=source_sha256,
                cubemx=process,
                diagnostics=diagnostics,
            )
        if not roundtrip_path.is_file():
            diagnostics.append(
                Diagnostic(
                    severity="error",
                    code="cubemx.roundtrip_missing",
                    message="STM32CubeMX did not create the round-trip IOC file.",
                )
            )
            return IocValidationResult(
                path=str(source_path),
                valid=False,
                source_sha256=source_sha256,
                cubemx=process,
                diagnostics=diagnostics,
            )

        roundtrip_content = roundtrip_path.read_bytes()
        roundtrip = IocDocument.parse(roundtrip_content.decode("utf-8-sig"))
        diagnostics.extend(roundtrip.diagnostics)
        diagnostics.extend(_compare_required_entries(requirements, roundtrip))
        valid = not any(item.severity == "error" for item in diagnostics)
        return IocValidationResult(
            path=str(source_path),
            valid=valid,
            source_sha256=source_sha256,
            roundtrip_sha256=hashlib.sha256(roundtrip_content).hexdigest(),
            cubemx=process,
            diagnostics=diagnostics,
        )


def validate_ioc_file(raw_path: str | Path, settings: Settings) -> IocValidationResult:
    """Validate an allowed IOC file without a source-file change."""
    path, content, _ = load_ioc_document(raw_path, settings)
    return validate_ioc_content(path, content, settings)
