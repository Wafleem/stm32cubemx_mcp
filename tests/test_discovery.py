from pathlib import Path

from stm32cubemx_mcp.discovery import discover_environment
from stm32cubemx_mcp.settings import Settings


def test_explicit_cubemx_path_is_discovered(tmp_path: Path) -> None:
    launcher = tmp_path / "STM32CubeMX.exe"
    launcher.touch()
    java = tmp_path / "jre" / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.touch()
    settings = Settings(allowed_roots=(tmp_path,), cubemx_path=launcher)

    report = discover_environment(settings, system_name="Windows", architecture="AMD64")

    match = next(item for item in report.cubemx if item.path == str(launcher))
    assert match.available
    assert match.invocation_prefix == [str(java), "-jar", str(launcher)]


def test_environment_reports_configured_roots(tmp_path: Path) -> None:
    settings = Settings(allowed_roots=(tmp_path,))

    report = discover_environment(settings, system_name="TestOS", architecture="test-arch")

    assert report.operating_system == "TestOS"
    assert report.architecture == "test-arch"
    assert report.allowed_roots == [str(tmp_path)]
