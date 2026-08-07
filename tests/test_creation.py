import hashlib
from pathlib import Path

import pytest

from stm32cubemx_mcp.creation import build_ioc_creation_script, create_ioc
from stm32cubemx_mcp.models import (
    CubeMXProcessResult,
    Diagnostic,
    IocCreateRequest,
    IocValidationResult,
)
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def _request(output_directory: Path, *, target_kind: str = "board") -> IocCreateRequest:
    return IocCreateRequest(
        target_kind=target_kind,
        target="NUCLEO-F401RE" if target_kind == "board" else "STM32F401RETx",
        output_directory=str(output_directory),
        project_name="f401_app",
    )


def _runner(
    commands: list[str], settings: Settings, work_directory: Path
) -> CubeMXProcessResult:
    del settings
    save_command = next(item for item in commands if item.startswith("config saveas"))
    ioc_path = Path(save_command.split('"', maxsplit=2)[1])
    assert ioc_path.parent == work_directory
    content = FIXTURE.read_text(encoding="utf-8")
    content += f"ProjectManager.ProjectLocation={work_directory}\n"
    ioc_path.write_text(content, encoding="utf-8")
    return CubeMXProcessResult(
        succeeded=True,
        exit_code=0,
        duration_seconds=0.01,
        stdout="OK\nOK\nOK\nOK\nOK\n",
    )


def _validator(
    source_path: Path, content: bytes, settings: Settings
) -> IocValidationResult:
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


def _materializing_validator(
    source_path: Path, content: bytes, settings: Settings
) -> IocValidationResult:
    result = _validator(source_path, content, settings)
    location_line = next(
        line
        for line in content.decode("utf-8").splitlines()
        if line.startswith("ProjectManager.ProjectLocation=")
    )
    destination = Path(location_line.split("=", maxsplit=1)[1])
    destination.mkdir()
    (destination / source_path.name).write_bytes(content)
    return result


def _materializing_invalid_validator(
    source_path: Path, content: bytes, settings: Settings
) -> IocValidationResult:
    result = _materializing_validator(source_path, content, settings)
    return result.model_copy(
        update={
            "valid": False,
            "diagnostics": [
                Diagnostic(
                    severity="error",
                    code="test.invalid",
                    message="The test validator rejected the IOC file.",
                )
            ],
        }
    )


def test_build_ioc_creation_script_uses_typed_board_and_mcu_commands(tmp_path: Path) -> None:
    board = _request(tmp_path / "board")
    mcu = _request(tmp_path / "mcu", target_kind="mcu")

    board_commands = build_ioc_creation_script(board, tmp_path, tmp_path / "board.ioc")
    mcu_commands = build_ioc_creation_script(mcu, tmp_path, tmp_path / "mcu.ioc")

    assert board_commands[0] == "loadboard NUCLEO-F401RE allmodes"
    assert mcu_commands[0] == "load STM32F401RETx"
    assert board_commands[-1] == "exit"
    assert mcu_commands[-1] == "exit"


def test_create_ioc_validates_and_promotes_one_new_directory(tmp_path: Path) -> None:
    destination = tmp_path / "created"
    request = _request(destination)
    settings = Settings(allowed_roots=(tmp_path,))

    result = create_ioc(
        request,
        settings,
        validator=_validator,
        script_runner=_runner,
    )

    ioc_path = destination / "f401_app.ioc"
    assert result.succeeded
    assert result.ioc_path == str(ioc_path)
    assert result.validation is not None
    assert result.validation.path == str(ioc_path)
    assert ioc_path.is_file()
    assert str(destination) in ioc_path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".*-ioc-*"))


def test_create_ioc_removes_stage_after_validation_failure(tmp_path: Path) -> None:
    destination = tmp_path / "created"
    request = _request(destination)
    settings = Settings(allowed_roots=(tmp_path,))

    result = create_ioc(
        request,
        settings,
        validator=_materializing_invalid_validator,
        script_runner=_runner,
    )

    assert not result.succeeded
    assert not destination.exists()
    assert [item.code for item in result.diagnostics] == ["creation.ioc_invalid"]
    assert not list(tmp_path.glob(".*-ioc-*"))


def test_create_ioc_accepts_the_exact_file_created_during_validation(tmp_path: Path) -> None:
    destination = tmp_path / "created"
    request = _request(destination)
    settings = Settings(allowed_roots=(tmp_path,))

    result = create_ioc(
        request,
        settings,
        validator=_materializing_validator,
        script_runner=_runner,
    )

    assert result.succeeded
    assert (destination / "f401_app.ioc").is_file()
    assert not list(tmp_path.glob(".*-ioc-*"))


def test_create_ioc_rejects_an_existing_output_directory(tmp_path: Path) -> None:
    destination = tmp_path / "created"
    destination.mkdir()
    request = _request(destination)
    settings = Settings(allowed_roots=(tmp_path,))

    with pytest.raises(FileExistsError, match="already exists"):
        create_ioc(request, settings, validator=_validator, script_runner=_runner)


@pytest.mark.parametrize("target", ["NUCLEO F401RE", 'NUCLEO-F401RE"\nexit'])
def test_create_request_rejects_free_form_target_text(tmp_path: Path, target: str) -> None:
    with pytest.raises(ValueError):
        IocCreateRequest(
            target_kind="board",
            target=target,
            output_directory=str(tmp_path / "created"),
            project_name="f401_app",
        )
