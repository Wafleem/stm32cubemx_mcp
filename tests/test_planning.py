from pathlib import Path

import pytest

from stm32cubemx_mcp.models import IocPinAssignment, IocPlanRequest
from stm32cubemx_mcp.planning import plan_ioc_changes
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def test_plan_adds_a_pin_peripheral_and_cmake_settings() -> None:
    settings = Settings(allowed_roots=(FIXTURE.parent.parent.resolve(),))
    request = IocPlanRequest(
        path=str(FIXTURE),
        pin_assignments=[IocPinAssignment(pin="PC10", signal="USART3_TX", label="CONSOLE_TX")],
        enabled_peripherals=["USART3"],
        parameter_updates={"USART3.BaudRate": "115200"},
        project_name="f401_console",
        toolchain="CMake",
    )
    source_before = FIXTURE.read_bytes()

    plan = plan_ioc_changes(request, settings)

    changes = {change.key: change.after for change in plan.changes}
    assert changes["Mcu.IP4"] == "USART3"
    assert changes["Mcu.IPNb"] == "5"
    assert changes["Mcu.Pin6"] == "PC10"
    assert changes["Mcu.PinsNb"] == "7"
    assert changes["PC10.Signal"] == "USART3_TX"
    assert changes["PC10.GPIO_Label"] == "CONSOLE_TX"
    assert changes["PC10.Locked"] == "true"
    assert changes["USART3.BaudRate"] == "115200"
    assert changes["ProjectManager.ToolChain"] == "CMake"
    assert "+PC10.Signal=USART3_TX" in plan.unified_diff
    assert plan.validation_status == "not_run"
    assert len(plan.plan_id) == 20
    assert FIXTURE.read_bytes() == source_before


def test_plan_changes_an_existing_pin_without_new_pin_index() -> None:
    settings = Settings(allowed_roots=(FIXTURE.parent.parent.resolve(),))
    request = IocPlanRequest(
        path=str(FIXTURE),
        pin_assignments=[IocPinAssignment(pin="PA5", signal="GPIO_Output", label="STATUS")],
    )

    plan = plan_ioc_changes(request, settings)

    changed_keys = {change.key for change in plan.changes}
    assert "PA5.GPIO_Label" in changed_keys
    assert not any(key.startswith("Mcu.Pin") for key in changed_keys)


def test_plan_protects_swd_pins_by_default() -> None:
    settings = Settings(allowed_roots=(FIXTURE.parent.parent.resolve(),))
    request = IocPlanRequest(
        path=str(FIXTURE),
        pin_assignments=[IocPinAssignment(pin="PA13", signal="GPIO_Output")],
    )

    with pytest.raises(ValueError, match="protected SWD pin PA13"):
        plan_ioc_changes(request, settings)


def test_parameter_updates_cannot_change_structural_pin_keys() -> None:
    settings = Settings(allowed_roots=(FIXTURE.parent.parent.resolve(),))
    request = IocPlanRequest(
        path=str(FIXTURE),
        parameter_updates={"Mcu.Pin0": "PB0"},
    )

    with pytest.raises(ValueError, match="structured pin or peripheral"):
        plan_ioc_changes(request, settings)
