import hashlib
import shutil
from pathlib import Path

import pytest

from stm32cubemx_mcp.models import (
    CubeMXProcessResult,
    IocValidationResult,
    RegenerationPlanRequest,
)
from stm32cubemx_mcp.regeneration import plan_project_regeneration, snapshot_project
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def _valid_validator(source_path: Path, content: bytes, settings: Settings) -> IocValidationResult:
    del settings
    digest = hashlib.sha256(content).hexdigest()
    return IocValidationResult(
        path=str(source_path),
        valid=True,
        source_sha256=digest,
        roundtrip_sha256=digest,
        cubemx=CubeMXProcessResult(
            succeeded=True,
            exit_code=0,
            duration_seconds=0.01,
        ),
    )


def _regeneration_runner(
    commands: list[str], settings: Settings, work_directory: Path
) -> CubeMXProcessResult:
    del commands, settings
    main = work_directory / "Core" / "Src" / "main.c"
    main.write_text(main.read_text(encoding="utf-8") + "// regenerated\n", encoding="utf-8")
    (work_directory / "Core" / "Src" / "gpio.c").write_text(
        "void MX_GPIO_Init(void) {}\n", encoding="utf-8"
    )
    (work_directory / "Core" / "Src" / "obsolete.c").unlink()
    return CubeMXProcessResult(
        succeeded=True,
        exit_code=0,
        duration_seconds=0.01,
        stdout="OK\nOK\nOK\nOK\nOK\n",
    )


def _cubeide_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "Core" / "Src").mkdir(parents=True)
    shutil.copy2(FIXTURE, project / "project.ioc")
    (project / ".project").write_text("<projectDescription/>\n", encoding="utf-8")
    (project / ".cproject").write_text("<cproject/>\n", encoding="utf-8")
    (project / "Core" / "Src" / "main.c").write_text("int main(void) {}\n", encoding="utf-8")
    (project / "Core" / "Src" / "obsolete.c").write_text(
        "void obsolete(void) {}\n", encoding="utf-8"
    )
    return project


def test_regeneration_plan_reports_file_changes_without_source_writes(
    tmp_path: Path,
) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    source_before = snapshot_project(project, settings)

    plan = plan_project_regeneration(
        RegenerationPlanRequest(project_directory=str(project)),
        settings,
        validator=_valid_validator,
        script_runner=_regeneration_runner,
    )

    changes = {item.path: item for item in plan.changes}
    assert changes["Core/Src/main.c"].change == "modified"
    assert changes["Core/Src/gpio.c"].change == "added"
    assert changes["Core/Src/obsolete.c"].change == "deleted"
    assert "+// regenerated" in changes["Core/Src/main.c"].unified_diff
    assert snapshot_project(project, settings) == source_before
    assert not list(tmp_path.glob(".*-regeneration-*"))
    assert [item.code for item in plan.diagnostics] == ["regeneration.preview_only"]


def test_regeneration_plan_requires_one_ioc_file(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    shutil.copy2(FIXTURE, project / "second.ioc")
    settings = Settings(allowed_roots=(tmp_path,))

    with pytest.raises(ValueError, match="must contain one IOC file"):
        plan_project_regeneration(
            RegenerationPlanRequest(project_directory=str(project)),
            settings,
            validator=_valid_validator,
            script_runner=_regeneration_runner,
        )


def test_regeneration_plan_enforces_project_file_limit(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,), max_project_files=2)

    with pytest.raises(ValueError, match="MAX_PROJECT_FILES"):
        plan_project_regeneration(
            RegenerationPlanRequest(project_directory=str(project)),
            settings,
            validator=_valid_validator,
            script_runner=_regeneration_runner,
        )
