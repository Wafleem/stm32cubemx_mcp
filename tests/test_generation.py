import hashlib
import shutil
from pathlib import Path

from stm32cubemx_mcp.generation import generate_project, promote_directory
from stm32cubemx_mcp.ioc import inspect_ioc
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


def _project_name_from_commands(commands: list[str]) -> str:
    return next(item for item in commands if item.startswith("project name ")).split()[-1]


def _write_required_files(container: Path, *, source_root: Path) -> None:
    (source_root / "Src").mkdir(parents=True, exist_ok=True)
    (source_root / "Inc").mkdir(parents=True, exist_ok=True)
    (source_root / "Src" / "main.c").write_text("int main(void) {}\n", encoding="utf-8")
    (source_root / "Inc" / "main.h").write_text("#pragma once\n", encoding="utf-8")
    cmsis = container / "Drivers" / "CMSIS" / "Include"
    cmsis.mkdir(parents=True, exist_ok=True)
    (cmsis / "core_cm4.h").write_text("#pragma once\n", encoding="utf-8")
    hal = container / "Drivers" / "STM32F4xx_HAL_Driver" / "Src"
    hal.mkdir(parents=True, exist_ok=True)
    (hal / "stm32f4xx_hal.c").write_text("void HAL_Init(void) {}\n", encoding="utf-8")


def _project_xml(project_name: str, links: list[tuple[str, str]] | None = None) -> str:
    linked_xml = ""
    if links:
        items = "".join(
            f"<link><name>{name}</name><type>1</type><locationURI>{uri}</locationURI></link>"
            for name, uri in links
        )
        linked_xml = f"<linkedResources>{items}</linkedResources>"
    return f"<projectDescription><name>{project_name}</name>{linked_xml}</projectDescription>\n"


def _cubeide_runner(
    commands: list[str], settings: Settings, work_directory: Path
) -> CubeMXProcessResult:
    del settings
    project_path = _path_from_command(
        next(item for item in commands if item.startswith("project path"))
    )
    assert project_path == work_directory
    project_name = _project_name_from_commands(commands)
    (project_path / ".project").write_text(_project_xml(project_name), encoding="utf-8")
    (project_path / ".cproject").write_text("<cproject/>\n", encoding="utf-8")
    _write_required_files(project_path, source_root=project_path / "Core")
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
    inspection = inspect_ioc(destination / "f401_app.ioc", settings)
    assert inspection.summary.project_name == "f401_app"
    assert inspection.summary.toolchain == "STM32CubeIDE"
    assert "ProjectManager.ProjectFileName=f401_app.ioc" in (
        destination / "f401_app.ioc"
    ).read_text(encoding="utf-8")
    assert "ProjectManager.UnderRoot=true" in (destination / "f401_app.ioc").read_text(
        encoding="utf-8"
    )
    assert source.read_bytes() == original
    assert not list(tmp_path.glob(".*-cubemx-*"))


def test_generate_project_restores_the_staged_ioc_if_cubemx_removes_it(
    tmp_path: Path,
) -> None:
    source = _project_copy(tmp_path)
    destination = tmp_path / "generated"
    settings = Settings(allowed_roots=(tmp_path,))

    def runner_without_ioc(
        commands: list[str], active_settings: Settings, work_directory: Path
    ) -> CubeMXProcessResult:
        result = _cubeide_runner(commands, active_settings, work_directory)
        (work_directory / "f401_app.ioc").unlink()
        return result

    result = generate_project(
        ProjectGenerationRequest(
            ioc_path=str(source),
            output_directory=str(destination),
            project_name="f401_app",
        ),
        settings,
        validator=_valid_validator,
        script_runner=runner_without_ioc,
    )

    assert result.succeeded
    assert (destination / "f401_app.ioc").is_file()


def test_generate_project_promotes_complete_nested_container(tmp_path: Path) -> None:
    source = _project_copy(tmp_path)
    destination = tmp_path / "generated"
    settings = Settings(allowed_roots=(tmp_path,))

    def nested_runner(
        commands: list[str], active_settings: Settings, work_directory: Path
    ) -> CubeMXProcessResult:
        del active_settings
        project_name = _project_name_from_commands(commands)
        _write_required_files(work_directory, source_root=work_directory)
        project_root = work_directory / project_name
        project_root.mkdir()
        links = [
            ("Application/User/main.c", "PARENT-1-PROJECT_LOC/Src/main.c"),
            (
                "Drivers/STM32F4xx_HAL_Driver/stm32f4xx_hal.c",
                "PARENT-1-PROJECT_LOC/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c",
            ),
            (f"{project_name}.ioc", f"PARENT-1-PROJECT_LOC/{project_name}.ioc"),
        ]
        (project_root / ".project").write_text(_project_xml(project_name, links), encoding="utf-8")
        (project_root / ".cproject").write_text("<cproject/>\n", encoding="utf-8")
        return CubeMXProcessResult(succeeded=True, exit_code=0, duration_seconds=0.01)

    result = generate_project(
        ProjectGenerationRequest(
            ioc_path=str(source),
            output_directory=str(destination),
            project_name="f401_app",
        ),
        settings,
        validator=_valid_validator,
        script_runner=nested_runner,
    )

    assert result.succeeded
    assert result.output_directory == str(destination)
    assert result.project_path == str(destination / "f401_app")
    assert (destination / "Src" / "main.c").is_file()
    assert (destination / "Inc" / "main.h").is_file()
    assert (destination / "Drivers" / "STM32F4xx_HAL_Driver" / "Src").is_dir()
    assert (destination / "f401_app" / ".project").is_file()


def test_generate_project_rejects_a_missing_linked_resource(tmp_path: Path) -> None:
    source = _project_copy(tmp_path)
    destination = tmp_path / "generated"
    settings = Settings(allowed_roots=(tmp_path,))

    def broken_runner(
        commands: list[str], active_settings: Settings, work_directory: Path
    ) -> CubeMXProcessResult:
        del active_settings
        project_name = _project_name_from_commands(commands)
        _write_required_files(work_directory, source_root=work_directory)
        project_root = work_directory / project_name
        project_root.mkdir()
        links = [("Application/User/missing.c", "PARENT-1-PROJECT_LOC/Src/missing.c")]
        (project_root / ".project").write_text(_project_xml(project_name, links), encoding="utf-8")
        (project_root / ".cproject").write_text("<cproject/>\n", encoding="utf-8")
        return CubeMXProcessResult(succeeded=True, exit_code=0, duration_seconds=0.01)

    result = generate_project(
        ProjectGenerationRequest(
            ioc_path=str(source),
            output_directory=str(destination),
            project_name="f401_app",
        ),
        settings,
        validator=_valid_validator,
        script_runner=broken_runner,
    )

    assert not result.succeeded
    assert not destination.exists()
    assert "generation.linked_resource_missing" in {item.code for item in result.diagnostics}


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


def test_promote_directory_accepts_a_completed_windows_rename(tmp_path: Path, monkeypatch) -> None:
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
