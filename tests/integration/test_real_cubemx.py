import os
from dataclasses import replace
from pathlib import Path

import pytest

from stm32cubemx_mcp.cubemx import run_cubemx_script, validate_ioc_content
from stm32cubemx_mcp.discovery import discover_environment
from stm32cubemx_mcp.generation import generate_project
from stm32cubemx_mcp.models import (
    IocValidationResult,
    ProjectGenerationRequest,
    RegenerationPlanRequest,
)
from stm32cubemx_mcp.regeneration import plan_project_regeneration, snapshot_project
from stm32cubemx_mcp.settings import Settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("CUBEMX_MCP_RUN_INTEGRATION") != "1",
        reason="Set CUBEMX_MCP_RUN_INTEGRATION=1 to run installed-tool tests.",
    ),
]


def _quoted(path: Path) -> str:
    return f'"{path}"'


def test_create_and_validate_nucleo_f401re_ioc(tmp_path: Path) -> None:
    settings = Settings.from_env()
    if not discover_environment(settings).cubemx:
        pytest.skip("STM32CubeMX is not installed.")

    project_path = tmp_path / "nucleo_f401re"
    ioc_path = project_path / "nucleo_f401re.ioc"
    project_path.mkdir()
    create_commands = [
        "loadboard NUCLEO-F401RE allmodes",
        "project name nucleo_f401re",
        "project toolchain STM32CubeIDE",
        f"project path {_quoted(project_path)}",
        f"config saveas {_quoted(ioc_path)}",
        "exit",
    ]

    create_result = run_cubemx_script(create_commands, settings, project_path)

    assert create_result.succeeded, create_result.stderr or create_result.stdout[-4000:]
    assert ioc_path.is_file()
    validation = validate_ioc_content(ioc_path, ioc_path.read_bytes(), settings)
    diagnostic_codes = [item.code for item in validation.diagnostics]
    assert validation.valid, diagnostic_codes

    generation_settings = replace(settings, allowed_roots=(tmp_path.resolve(),))

    def use_previous_validation(
        source_path: Path, content: bytes, active_settings: Settings
    ) -> IocValidationResult:
        del source_path, content, active_settings
        return validation

    generated_path = tmp_path / "generated"
    generation = generate_project(
        ProjectGenerationRequest(
            ioc_path=str(ioc_path),
            output_directory=str(generated_path),
            project_name="nucleo_f401re_app",
        ),
        generation_settings,
        validator=use_previous_validation,
    )

    generation_codes = [item.code for item in generation.diagnostics]
    assert generation.succeeded, generation_codes
    assert (generated_path / ".project").is_file()
    assert (generated_path / ".cproject").is_file()
    assert any(path.endswith(".ioc") for path in generation.generated_files)

    source_before = snapshot_project(generated_path, generation_settings)
    regeneration = plan_project_regeneration(
        RegenerationPlanRequest(project_directory=str(generated_path)),
        generation_settings,
        validator=use_previous_validation,
    )

    assert regeneration.cubemx.succeeded
    assert regeneration.source_manifest_sha256
    assert regeneration.planned_manifest_sha256
    assert snapshot_project(generated_path, generation_settings) == source_before
    assert not list(tmp_path.glob(".*-regeneration-*"))
