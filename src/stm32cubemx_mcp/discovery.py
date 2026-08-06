from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

from stm32cubemx_mcp.models import Diagnostic, EnvironmentReport, ExecutableInfo
from stm32cubemx_mcp.settings import Settings


def _deduplicate(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _cubemx_candidates(settings: Settings, system_name: str) -> list[Path]:
    candidates: list[Path] = []
    if settings.cubemx_path is not None:
        candidates.append(settings.cubemx_path)

    if system_name == "Windows":
        candidates.extend(
            [
                Path("C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeMX/STM32CubeMX.exe"),
                Path("C:/Program Files/STMicroelectronics/STM32CubeMX/STM32CubeMX.exe"),
                Path("C:/ST/STM32CubeMX/STM32CubeMX.exe"),
            ]
        )
    elif system_name == "Darwin":
        app_roots = [
            Path("/Applications/STMicroelectronics/STM32Cube/STM32CubeMX/STM32CubeMX.app"),
            Path("/Applications/STM32CubeMX.app"),
            Path.home() / "Applications/STM32CubeMX.app",
        ]
        for app_root in app_roots:
            candidates.append(app_root / "Contents/MacOS/STM32CubeMX")
            candidates.append(app_root / "Contents/MacOs/STM32CubeMX")

    path_match = shutil.which("STM32CubeMX") or shutil.which("stm32cubemx")
    if path_match:
        candidates.append(Path(path_match))
    return _deduplicate(candidates)


def _cubeide_candidates(system_name: str) -> list[Path]:
    candidates: list[Path] = []
    if system_name == "Windows":
        for base in (Path("C:/ST"), Path("C:/Program Files/STMicroelectronics/STM32Cube")):
            if base.exists():
                candidates.extend(base.glob("STM32CubeIDE*/STM32CubeIDE/stm32cubeide.exe"))
                candidates.extend(base.glob("STM32CubeIDE*/stm32cubeide.exe"))
    elif system_name == "Darwin":
        candidates.extend(
            [
                Path("/Applications/STM32CubeIDE.app/Contents/MacOS/stm32cubeide"),
                Path(
                    "/Applications/STMicroelectronics/STM32Cube/STM32CubeIDE/"
                    "STM32CubeIDE.app/Contents/MacOS/stm32cubeide"
                ),
            ]
        )

    path_match = shutil.which("stm32cubeide")
    if path_match:
        candidates.append(Path(path_match))
    return _deduplicate(candidates)


def _version_from_path(path: Path) -> str | None:
    match = re.search(r"(?:STM32CubeIDE[_-]|STM32CubeMX[_-])([0-9]+(?:\.[0-9]+)+)", str(path), re.I)
    return match.group(1) if match else None


def _cubemx_info(path: Path, system_name: str) -> ExecutableInfo:
    if system_name == "Windows":
        java = path.parent / "jre" / "bin" / "java.exe"
        invocation = [str(java), "-jar", str(path)] if java.is_file() else [str(path)]
    else:
        invocation = [str(path)]
    return ExecutableInfo(
        name="STM32CubeMX",
        available=True,
        path=str(path),
        version=_version_from_path(path),
        invocation_prefix=invocation,
    )


def _which_info(name: str, command: str) -> ExecutableInfo:
    path = shutil.which(command)
    return ExecutableInfo(
        name=name,
        available=path is not None,
        path=path,
        invocation_prefix=[path] if path else [],
    )


def discover_environment(
    settings: Settings,
    *,
    system_name: str | None = None,
    architecture: str | None = None,
) -> EnvironmentReport:
    current_system = system_name or platform.system()
    current_architecture = architecture or platform.machine()
    diagnostics: list[Diagnostic] = []

    cubemx = [
        _cubemx_info(path, current_system)
        for path in _cubemx_candidates(settings, current_system)
        if path.is_file()
    ]
    if not cubemx:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="cubemx.not_found",
                message=("STM32CubeMX was not found. Set CUBEMX_MCP_CUBEMX_PATH to its launcher."),
            )
        )

    cubeide = [
        ExecutableInfo(
            name="STM32CubeIDE",
            available=True,
            path=str(path),
            version=_version_from_path(path),
            invocation_prefix=[str(path)],
        )
        for path in _cubeide_candidates(current_system)
        if path.is_file()
    ]
    if not cubeide:
        diagnostics.append(
            Diagnostic(
                severity="info",
                code="cubeide.not_found",
                message="STM32CubeIDE was not found; CubeIDE builds will be unavailable.",
            )
        )

    return EnvironmentReport(
        operating_system=current_system,
        architecture=current_architecture,
        python_version=platform.python_version(),
        python_executable=sys.executable,
        cubemx=cubemx,
        cubeide=cubeide,
        cmake=_which_info("CMake", "cmake"),
        ninja=_which_info("Ninja", "ninja"),
        allowed_roots=[str(root) for root in settings.allowed_roots],
        diagnostics=diagnostics,
    )
