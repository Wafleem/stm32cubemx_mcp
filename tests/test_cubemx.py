import shutil
from pathlib import Path

from stm32cubemx_mcp.cubemx import (
    build_cubemx_command,
    build_validation_script,
    validate_ioc_content,
)
from stm32cubemx_mcp.models import CubeMXProcessResult, ExecutableInfo
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def _path_from_script_command(command: str) -> Path:
    return Path(command.split('"', maxsplit=2)[1])


def _copy_runner(
    commands: list[str], settings: Settings, work_directory: Path
) -> CubeMXProcessResult:
    del settings, work_directory
    shutil.copy2(_path_from_script_command(commands[0]), _path_from_script_command(commands[2]))
    return CubeMXProcessResult(
        succeeded=True,
        exit_code=0,
        duration_seconds=0.01,
        stdout="OK\nOK\n",
    )


def _mismatch_runner(
    commands: list[str], settings: Settings, work_directory: Path
) -> CubeMXProcessResult:
    del settings, work_directory
    source = _path_from_script_command(commands[0]).read_text(encoding="utf-8")
    output = source.replace("PA5.Signal=GPIO_Output", "PA5.Signal=GPIO_Input")
    _path_from_script_command(commands[2]).write_text(output, encoding="utf-8")
    return CubeMXProcessResult(
        succeeded=True,
        exit_code=0,
        duration_seconds=0.01,
        stdout="OK\nOK\n",
    )


def test_build_cubemx_command_uses_quiet_script_mode(tmp_path: Path) -> None:
    executable = ExecutableInfo(
        name="STM32CubeMX",
        available=True,
        path="C:/STM32CubeMX/STM32CubeMX.exe",
        invocation_prefix=["C:/STM32CubeMX/jre/bin/java.exe", "-jar", "STM32CubeMX.exe"],
    )
    script = tmp_path / "commands.mxscript"

    command = build_cubemx_command(executable, script)

    assert command[-2:] == ["-q", str(script)]


def test_build_validation_script_quotes_paths(tmp_path: Path) -> None:
    input_path = tmp_path / "input file.ioc"
    output_path = tmp_path / "output file.ioc"

    commands = build_validation_script(input_path, output_path)

    assert commands == [
        f'config load "{input_path}"',
        f'project path "{tmp_path}"',
        f'config saveas "{output_path}"',
        "exit",
    ]


def test_validate_ioc_content_accepts_preserved_settings(tmp_path: Path) -> None:
    source_path = tmp_path / FIXTURE.name
    shutil.copy2(FIXTURE, source_path)
    content = source_path.read_bytes()
    settings = Settings(allowed_roots=(tmp_path,))

    result = validate_ioc_content(
        source_path,
        content,
        settings,
        script_runner=_copy_runner,
    )

    assert result.valid
    assert result.roundtrip_sha256 == result.source_sha256


def test_validate_ioc_content_rejects_changed_required_setting(tmp_path: Path) -> None:
    source_path = tmp_path / FIXTURE.name
    shutil.copy2(FIXTURE, source_path)
    content = source_path.read_bytes()
    settings = Settings(allowed_roots=(tmp_path,))

    result = validate_ioc_content(
        source_path,
        content,
        settings,
        required_entries={"PA5.Signal": "GPIO_Output"},
        script_runner=_mismatch_runner,
    )

    assert not result.valid
    assert any(item.code == "ioc.roundtrip_mismatch" for item in result.diagnostics)


def test_validate_ioc_content_uses_a_directory_outside_the_source_project(
    tmp_path: Path,
) -> None:
    source_project = tmp_path / "project"
    source_project.mkdir()
    source_path = source_project / FIXTURE.name
    shutil.copy2(FIXTURE, source_path)
    before = {path.name for path in source_project.iterdir()}
    settings = Settings(allowed_roots=(tmp_path,))

    def isolated_runner(
        commands: list[str], active_settings: Settings, work_directory: Path
    ) -> CubeMXProcessResult:
        del active_settings
        staged_source = _path_from_script_command(commands[0])
        assert work_directory == staged_source.parent
        assert work_directory.parent != source_project
        shutil.copy2(staged_source, _path_from_script_command(commands[2]))
        return CubeMXProcessResult(
            succeeded=True,
            exit_code=0,
            duration_seconds=0.01,
            stdout="OK\nOK\n",
        )

    result = validate_ioc_content(
        source_path,
        source_path.read_bytes(),
        settings,
        script_runner=isolated_runner,
    )

    assert result.valid
    assert {path.name for path in source_project.iterdir()} == before
