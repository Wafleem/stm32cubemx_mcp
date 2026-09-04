import plistlib
from pathlib import Path

from stm32cubemx_mcp.discovery import _cubemx_candidates, _deduplicate, discover_environment
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


def test_discovery_deduplicates_canonical_paths(tmp_path: Path) -> None:
    launcher = tmp_path / "STM32CubeMX"
    equivalent = tmp_path / "nested" / ".." / "STM32CubeMX"

    assert _deduplicate([launcher, equivalent]) == [launcher]


def test_macos_candidates_include_stmicroelectronics_application_path(tmp_path: Path) -> None:
    settings = Settings(allowed_roots=(tmp_path,))

    candidates = _cubemx_candidates(settings, "Darwin")

    assert (
        Path("/Applications/STMicroelectronics/STM32CubeMX.app")
        / "Contents"
        / "MacOS"
        / "STM32CubeMX"
    ) in candidates


def test_macos_bundle_reports_version_and_native_launcher(tmp_path: Path) -> None:
    app_root = tmp_path / "STM32CubeMX.app"
    launcher = app_root / "Contents" / "MacOS" / "STM32CubeMX"
    launcher.parent.mkdir(parents=True)
    launcher.touch()
    with (app_root / "Contents" / "Info.plist").open("wb") as info_file:
        plistlib.dump({"CFBundleShortVersionString": "6.18"}, info_file)
    settings = Settings(allowed_roots=(tmp_path,), cubemx_path=launcher)

    report = discover_environment(settings, system_name="Darwin", architecture="arm64")

    match = next(item for item in report.cubemx if item.path == str(launcher))
    assert match.version == "6.18"
    assert match.invocation_prefix == [str(launcher)]
    assert sum(item.path == str(launcher) for item in report.cubemx) == 1
