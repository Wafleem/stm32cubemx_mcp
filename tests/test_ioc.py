from pathlib import Path

from stm32cubemx_mcp.ioc import IocDocument, inspect_ioc, list_ioc_files
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def test_inspect_ioc_returns_semantic_summary() -> None:
    settings = Settings(allowed_roots=(FIXTURE.parent.parent.resolve(),))

    inspection = inspect_ioc(FIXTURE, settings)

    summary = inspection.summary
    assert summary.mcu_part_number == "STM32F401RET6"
    assert summary.mcu_family == "STM32F4"
    assert summary.board == "NUCLEO-F401RE"
    assert summary.project_name == "nucleo_f401re"
    assert summary.toolchain == "STM32CubeIDE"
    assert summary.peripherals == ["NVIC", "RCC", "SYS", "USART2"]
    assert summary.clock_values_hz["RCC.AHBFreq_Value"] == 84_000_000
    led = next(pin for pin in summary.pins if pin.pin == "PA5")
    assert led.label == "LD2"
    assert led.signal == "GPIO_Output"
    assert led.locked
    assert len(summary.source_sha256) == 64
    assert not inspection.diagnostics


def test_parser_reports_duplicate_and_malformed_lines() -> None:
    document = IocDocument.parse("Mcu.Name=first\nnot-an-entry\nMcu.Name=second\n")

    assert document.entries["Mcu.Name"] == "second"
    assert [diagnostic.code for diagnostic in document.diagnostics] == [
        "ioc.malformed_line",
        "ioc.duplicate_key",
    ]


def test_list_ioc_files_honors_limit(tmp_path: Path) -> None:
    for name in ("a.ioc", "b.ioc"):
        (tmp_path / name).write_text("Mcu.Name=STM32F4\n", encoding="utf-8")
    settings = Settings(allowed_roots=(tmp_path,))

    result = list_ioc_files(tmp_path, settings, limit=1)

    assert len(result.files) == 1
    assert result.truncated
