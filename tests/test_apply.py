import shutil
from pathlib import Path

import pytest

from stm32cubemx_mcp.apply import apply_ioc_changes
from stm32cubemx_mcp.models import IocApplyRequest, IocPinAssignment, IocPlanRequest
from stm32cubemx_mcp.planning import plan_ioc_changes
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def _project_copy(tmp_path: Path) -> Path:
    target = tmp_path / FIXTURE.name
    shutil.copy2(FIXTURE, target)
    return target


def test_apply_creates_backup_and_replaces_ioc(tmp_path: Path) -> None:
    target = _project_copy(tmp_path)
    original = target.read_bytes()
    settings = Settings(allowed_roots=(tmp_path,))
    plan_request = IocPlanRequest(
        path=str(target),
        pin_assignments=[IocPinAssignment(pin="PA5", signal="GPIO_Output", label="STATUS")],
    )
    plan = plan_ioc_changes(plan_request, settings)

    result = apply_ioc_changes(
        IocApplyRequest(
            plan_request=plan_request,
            expected_source_sha256=plan.source_sha256,
        ),
        settings,
    )

    assert result.changed
    assert result.applied_sha256 == plan.planned_sha256
    assert result.backup_path is not None
    assert Path(result.backup_path).read_bytes() == original
    assert "PA5.GPIO_Label=STATUS" in target.read_text(encoding="utf-8")


def test_apply_rejects_a_stale_source_hash(tmp_path: Path) -> None:
    target = _project_copy(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    plan_request = IocPlanRequest(
        path=str(target),
        parameter_updates={"USART2.BaudRate": "115200"},
    )
    plan = plan_ioc_changes(plan_request, settings)
    target.write_text(target.read_text(encoding="utf-8") + "User.Change=true\n", encoding="utf-8")
    changed_source = target.read_bytes()

    with pytest.raises(ValueError, match="source hash changed"):
        apply_ioc_changes(
            IocApplyRequest(
                plan_request=plan_request,
                expected_source_sha256=plan.source_sha256,
            ),
            settings,
        )

    assert target.read_bytes() == changed_source
    assert not list(tmp_path.glob("*.bak.*"))


def test_apply_of_no_changes_does_not_create_backup(tmp_path: Path) -> None:
    target = _project_copy(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    plan_request = IocPlanRequest(path=str(target), toolchain="STM32CubeIDE")
    plan = plan_ioc_changes(plan_request, settings)

    result = apply_ioc_changes(
        IocApplyRequest(
            plan_request=plan_request,
            expected_source_sha256=plan.source_sha256,
        ),
        settings,
    )

    assert not result.changed
    assert result.backup_path is None
    assert not list(tmp_path.glob("*.bak.*"))
