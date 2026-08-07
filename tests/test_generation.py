import hashlib
import shutil
from pathlib import Path

from stm32cubemx_mcp.generation import generate_project, promote_directory
from stm32cubemx_mcp.models import (
    CubeMXProcessResult,
    Diagnostic,
    IocValidationResult,
    ProjectGenerationRequest,
)
from stm32cubemx_mcp.settings import Settings

FIXTURE = Path(__file__).parent / "fixtures" / "nucleo_f401re.ioc"


def _validation(
    source_path: Path,
    content: bytes,
    settings: Settings,
    *,
    valid: bool = True,
) -> IocValidationResult:
    del settings
    digest = hashlib.sha256(content).hexdigest()
    diagnostics = []
    if not valid:
        diagnostics.append(
            Diagnostic(
                severity="error",
                code="test.invalid",
                message="The test validator rejected the IOC file.",
            )
        )
    return IocValidationResult(
        path=str(source_path),
        valid=valid,
        source_sha256=digest,
        roundtrip_sha256=digest if valid else None,
        cubemx=CubeMXProcessResult(
            succeeded=valid,
            exit_code=0 if valid else 1,
            duration_seconds=0.01,
        ),
        diagnostics=diagnostics,
    )


def _valid_validator(source_path: Path, content: bytes, settings: Settings) -> IocValidationResult:
    return _validation(source_path, content, settings)


def _invalid_validator(
    source_path: Path, content: bytes, settings: Settings
) -> IocValidationResult:
    return _validation(source_path, content, settings, valid=False)


def _path_from_command(command: str) -> Path:
    return Path(command.split('"', maxsplit=2)[1])


def _cubeide_runner(
    commands: list[str], settings: Settings, work_directory: Path
) -> CubeMXProcessResult:
    del settings
    project_path = _path_from_command(
        next(item for item in commands if item.startswith("project path"))
    )
    assert project_path == work_directory
    (project_path / ".project").write_text("<projectDescription/>\n", encoding="utf-8")
    (project_path / ".cproject").write_text("<cproject/>\n", encoding="utf-8")
    (project_path / "Core" / "Src").mkdir(parents=True)
    (project_path / "Core" / "Src" / "main.c").write_text("int main(void) {}\n", encoding="utf-8")
    (project_path / "Drivers").mkdir()
    return CubeMXProcessResult(
        succeeded=True,
        exit_code=0,
        duration_seconds=0.01,
        stdout="OK\nOK\nOK\nOK\nOK\n",
    )


def _project_copy(tmp_path: Path) -> Path:
    source = tmp_path / FIXTURE.name
    shutil.copy2(FIXTURE, source)
    return source


def test_generate_project_promotes_complete_cubeide_project(tmp_path: Path) -> None:
    source = _project_copy(tmp_path)
    original = source.read_bytes()
    destination = tmp_path / "generated"
    settings = Settings(allowed_roots=(tmp_path,))
    request = ProjectGenerationRequest(
        ioc_path=str(source),
        output_directory=str(destination),
        project_name="f401_app",
    )

    result = generate_project(
        request,
        settings,
        validator=_valid_validator,
        script_runner=_cubeide_runner,
    )

    assert result.succeeded
    assert destination.is_dir()
    assert (destination / ".project").is_file()
    assert (destination / ".cproject").is_file()
    assert (destination / "f401_app.ioc").is_file()
    assert "Core/Src/main.c" in result.generated_files
    assert source.read_bytes() == original
    assert not list(tmp_path.glob(".*-cubemx-*"))


def test_generate_project_stops_after_invalid_ioc(tmp_path: Path) -> None:
    source = _project_copy(tmp_path)
    destination = tmp_path / "generated"
    settings = Settings(allowed_roots=(tmp_path,))
    request = ProjectGenerationRequest(
        ioc_path=str(source),
        output_directory=str(destination),
        project_name="f401_app",
    )

    result = generate_project(request, settings, validator=_invalid_validator)

    assert not result.succeeded
    assert not destination.exists()
    assert [item.code for item in result.diagnostics] == ["generation.ioc_invalid"]


def test_generate_project_rejects_existing_output_directory(tmp_path: Path) -> None:
    source = _project_copy(tmp_path)
    destination = tmp_path / "generated"
    destination.mkdir()
    settings = Settings(allowed_roots=(tmp_path,))
    request = ProjectGenerationRequest(
        ioc_path=str(source),
        output_directory=str(destination),
        project_name="f401_app",
    )

    try:
        generate_project(request, settings, validator=_valid_validator)
    except FileExistsError as error:
        assert "already exists" in str(error)
    else:
        raise AssertionError("Generation accepted an existing output directory.")


def test_promote_directory_accepts_a_completed_windows_rename(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "stage"
    destination = tmp_path / "output"
    source.mkdir()
    original_replace = Path.replace

    def move_then_report_permission_error(path: Path, target: Path) -> Path:
        original_replace(path, target)
        raise PermissionError("The Windows rename reported a late error.")

    monkeypatch.setattr(Path, "replace", move_then_report_permission_error)

    promote_directory(source, destination)

    assert destination.is_dir()
    assert not source.exists()
