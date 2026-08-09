import os
from dataclasses import replace
from pathlib import Path

import pytest

from stm32cubemx_mcp.creation import create_ioc
from stm32cubemx_mcp.discovery import discover_environment
from stm32cubemx_mcp.generation import generate_project, validate_generated_project
from stm32cubemx_mcp.ioc import inspect_ioc
from stm32cubemx_mcp.models import (
    IocCreateRequest,
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


def test_create_and_validate_nucleo_f401re_ioc(tmp_path: Path) -> None:
    settings = Settings.from_env()
    if not discover_environment(settings).cubemx:
        pytest.skip("STM32CubeMX is not installed.")

    project_path = tmp_path / "nucleo_f401re"
    ioc_path = project_path / "nucleo_f401re.ioc"
    creation_settings = replace(settings, allowed_roots=(tmp_path.resolve(),))
    creation = create_ioc(
        IocCreateRequest(
            target_kind="board",
            target="NUCLEO-F401RE",
            output_directory=str(project_path),
            project_name="nucleo_f401re",
        ),
        creation_settings,
    )

    assert creation.succeeded, creation.diagnostics
    assert ioc_path.is_file()
    assert creation.validation is not None
    validation = creation.validation
    diagnostic_codes = [item.code for item in validation.diagnostics]
    assert validation.valid, diagnostic_codes

    generation_settings = replace(settings, allowed_roots=(tmp_path.resolve(),))

    generated_path = tmp_path / "generated"
    generation = generate_project(
        ProjectGenerationRequest(
            ioc_path=str(ioc_path),
            output_directory=str(generated_path),
            project_name="nucleo_f401re_app",
        ),
        generation_settings,
    )

    generation_codes = [item.code for item in generation.diagnostics]
    assert generation.succeeded, generation_codes
    project_root = Path(generation.project_path)
    assert Path(generation.output_directory) == generated_path
    assert project_root.is_relative_to(generated_path)
    assert (project_root / ".project").is_file()
    assert (project_root / ".cproject").is_file()
    assert any(path.endswith(".ioc") for path in generation.generated_files)
    assert any(path.name == "main.c" for path in generated_path.rglob("main.c"))
    assert any(path.name == "main.h" for path in generated_path.rglob("main.h"))
    assert any(path.name.startswith("core_cm") for path in generated_path.rglob("core_cm*.h"))
    assert any(path.name.endswith("_hal.c") for path in generated_path.rglob("*_hal.c"))
    assert not validate_generated_project(generated_path, project_root, "nucleo_f401re_app")
    generated_ioc = project_root / "nucleo_f401re_app.ioc"
    inspection = inspect_ioc(generated_ioc, generation_settings)
    assert inspection.summary.project_name == "nucleo_f401re_app"
    assert inspection.summary.toolchain == "STM32CubeIDE"
    assert "ProjectManager.ProjectFileName=nucleo_f401re_app.ioc" in (
        generated_ioc.read_text(encoding="utf-8")
    )

    source_before = snapshot_project(project_root, generation_settings)
    regeneration = plan_project_regeneration(
        RegenerationPlanRequest(project_directory=str(project_root)),
        generation_settings,
    )

    assert regeneration.succeeded, regeneration.diagnostics
    assert regeneration.validation is not None
    assert regeneration.validation.valid
    assert regeneration.cubemx is not None
    assert regeneration.cubemx.succeeded
    assert regeneration.source_manifest_sha256
    assert regeneration.planned_manifest_sha256
    assert not any(change.path.startswith("nucleo_f401re_app/") for change in regeneration.changes)
    assert snapshot_project(project_root, generation_settings) == source_before
    assert not (project_root / "roundtrip" / "roundtrip.ioc").exists()
    assert not list(tmp_path.glob(".*-regeneration-*"))
