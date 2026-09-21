import hashlib
import shutil
from pathlib import Path

import pytest

from stm32cubemx_mcp.models import (
    CubeMXProcessResult,
    IocValidationResult,
    RegenerationApplyRequest,
    RegenerationPlanRequest,
)
from stm32cubemx_mcp.regeneration import plan_project_regeneration, snapshot_project
from stm32cubemx_mcp.regeneration_apply import apply_project_regeneration
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
    del settings
    project_name = next(item for item in commands if item.startswith("project name ")).split()[-1]
    project_path = Path(
        next(item for item in commands if item.startswith("project path ")).split('"', maxsplit=2)[
            1
        ]
    )
    assert project_path == work_directory
    project_root = work_directory / project_name
    main = project_root / "Core" / "Src" / "main.c"
    main.write_text(main.read_text(encoding="utf-8") + "// regenerated\n", encoding="utf-8")
    (project_root / "Core" / "Src" / "gpio.c").write_text(
        "void MX_GPIO_Init(void) {}\n", encoding="utf-8"
    )
    (project_root / "Core" / "Src" / "obsolete.c").unlink()
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

    assert plan.succeeded
    changes = {item.path: item for item in plan.changes}
    assert changes["Core/Src/main.c"].change == "modified"
    assert changes["Core/Src/gpio.c"].change == "added"
    assert changes["Core/Src/obsolete.c"].change == "deleted"
    assert "+// regenerated" in changes["Core/Src/main.c"].unified_diff
    assert not any(item.path.startswith("nucleo_f401re/") for item in plan.changes)
    assert snapshot_project(project, settings) == source_before
    assert not list(tmp_path.glob(".*-regeneration-*"))
    assert [item.code for item in plan.diagnostics] == ["regeneration.preview_only"]


def test_regeneration_reports_a_source_change_created_by_validation(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))

    def source_writing_validator(
        source_path: Path, content: bytes, active_settings: Settings
    ) -> IocValidationResult:
        result = _valid_validator(source_path, content, active_settings)
        unexpected = project / "roundtrip" / "roundtrip.ioc"
        unexpected.parent.mkdir()
        unexpected.write_bytes(content)
        return result

    plan = plan_project_regeneration(
        RegenerationPlanRequest(project_directory=str(project)),
        settings,
        validator=source_writing_validator,
        script_runner=_regeneration_runner,
    )

    assert not plan.succeeded
    assert plan.plan_id is None
    assert plan.cubemx is None
    assert [item.code for item in plan.diagnostics] == [
        "regeneration.source_changed_after_validation"
    ]
    assert "roundtrip/roundtrip.ioc" in plan.diagnostics[0].message


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


def _approved_request(project: Path, settings: Settings, runner=_regeneration_runner):
    request = RegenerationPlanRequest(project_directory=str(project))
    plan = plan_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=runner
    )
    assert plan.succeeded
    return RegenerationApplyRequest(
        plan_request=request,
        expected_plan_id=plan.plan_id,
        expected_source_manifest_sha256=plan.source_manifest_sha256,
        expected_planned_manifest_sha256=plan.planned_manifest_sha256,
    )


def test_apply_regeneration_updates_files_and_preserves_unrelated_content(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(project.resolve(),))
    for relative in (".git/config", "Debug/application.elf", "notes.txt"):
        path = project / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text("preserve me\n")
    main = project / "Core/Src/main.c"
    main.chmod(0o640)
    original = main.read_bytes()
    request = _approved_request(project, settings)
    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=_regeneration_runner
    )
    assert result.succeeded and result.changed
    assert result.applied_manifest_sha256 == request.expected_planned_manifest_sha256
    assert main.read_bytes() == original + b"// regenerated\n"
    assert main.stat().st_mode & 0o777 == 0o640
    assert (project / "Core/Src/gpio.c").is_file()
    assert not (project / "Core/Src/obsolete.c").exists()
    assert (Path(result.backup_path) / "files/Core/Src/main.c").read_bytes() == original
    assert (Path(result.backup_path) / "files/Core/Src/obsolete.c").is_file()
    assert (Path(result.backup_path) / "transaction.json").is_file()
    assert not (project / ".cubemx-mcp-regeneration/apply.lock").exists()
    for relative in (".git/config", "Debug/application.elf", "notes.txt"):
        assert (project / relative).read_text() == "preserve me\n"


def test_apply_rejects_stale_regeneration_source_without_running_cubemx(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    (project / "notes.txt").write_text("new work")
    before = snapshot_project(project, settings)
    with pytest.raises(ValueError, match="source project changed"):
        apply_project_regeneration(request, settings)
    assert snapshot_project(project, settings) == before
    assert not (project / ".cubemx-mcp-regeneration").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_plan_id", "0" * 20),
        ("expected_planned_manifest_sha256", "0" * 64),
    ],
)
def test_apply_rejects_a_different_approved_plan(tmp_path: Path, field: str, value: str) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings).model_copy(update={field: value})
    before = snapshot_project(project, settings)
    with pytest.raises(ValueError, match="differs from the approved plan"):
        apply_project_regeneration(
            request, settings, validator=_valid_validator, script_runner=_regeneration_runner
        )
    assert snapshot_project(project, settings) == before
    assert not list(project.glob(".cubemx-mcp-regeneration/backup-*"))


def test_apply_rejects_different_generation_output(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    before = snapshot_project(project, settings)

    def changed_runner(commands, active_settings, work_directory):
        result = _regeneration_runner(commands, active_settings, work_directory)
        next(work_directory.rglob("main.c")).write_text("unexpected generation\n")
        return result

    with pytest.raises(ValueError, match="differs from the approved plan"):
        apply_project_regeneration(
            request, settings, validator=_valid_validator, script_runner=changed_runner
        )
    assert snapshot_project(project, settings) == before


def test_apply_stops_after_cube_validation_failure(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    before = snapshot_project(project, settings)

    def invalid_validator(*args):
        return _valid_validator(*args).model_copy(update={"valid": False})

    result = apply_project_regeneration(request, settings, validator=invalid_validator)
    assert not result.succeeded
    assert result.backup_path is None
    assert snapshot_project(project, settings) == before


def test_apply_detects_source_edit_during_generation(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)

    def editing_runner(*args):
        result = _regeneration_runner(*args)
        (project / "notes.txt").write_text("concurrent edit")
        return result

    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=editing_runner
    )
    assert not result.succeeded
    assert result.backup_path is None
    assert (project / "notes.txt").read_text() == "concurrent edit"
    assert (project / "Core/Src/obsolete.c").is_file()


def test_apply_rolls_back_partial_writes(tmp_path: Path, monkeypatch) -> None:
    from stm32cubemx_mcp import regeneration_apply

    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    before = snapshot_project(project, settings)
    replace = regeneration_apply._replace_file

    def fail_after_replacement(source, target):
        replace(source, target)
        if source.name == "main.c" and "files" not in source.parts:
            raise OSError("Simulated disk failure")

    monkeypatch.setattr(regeneration_apply, "_replace_file", fail_after_replacement)
    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=_regeneration_runner
    )
    assert not result.succeeded
    assert result.rolled_back
    assert not result.recovery_required
    assert snapshot_project(project, settings) == before
    assert Path(result.backup_path).is_dir()
    assert not (project / ".cubemx-mcp-regeneration/apply.lock").exists()


def test_rollback_preserves_concurrent_changes(tmp_path: Path, monkeypatch) -> None:
    from stm32cubemx_mcp import regeneration_apply

    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    replace = regeneration_apply._replace_file

    def fail_with_external_edit(source, target):
        replace(source, target)
        if target.name == "main.c":
            target.write_text("concurrent work\n")
            raise OSError("Simulated failure with concurrent work")

    monkeypatch.setattr(regeneration_apply, "_replace_file", fail_with_external_edit)
    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=_regeneration_runner
    )
    assert not result.succeeded
    assert not result.rolled_back
    assert result.recovery_required
    assert (project / "Core/Src/main.c").read_text() == "concurrent work\n"
    assert not (project / "Core/Src/gpio.c").exists()
    assert "Core/Src/main.c" in result.diagnostics[-1].message


def test_apply_no_changes_does_not_create_backup(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))

    def unchanged_runner(*args):
        return CubeMXProcessResult(succeeded=True, exit_code=0, duration_seconds=0.01)

    request = _approved_request(project, settings, unchanged_runner)
    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=unchanged_runner
    )
    assert result.succeeded and not result.changed
    assert result.backup_path is None


def test_apply_refuses_an_existing_lock(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    state = project / ".cubemx-mcp-regeneration"
    state.mkdir()
    (state / "apply.lock").write_text("existing lock")
    with pytest.raises(ValueError, match="regeneration lock exists"):
        apply_project_regeneration(request, settings)
    assert (state / "apply.lock").read_text() == "existing lock"


def test_apply_refuses_linked_backup_directory(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (project / ".cubemx-mcp-regeneration").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable.")
    with pytest.raises(ValueError, match="cannot be a link"):
        apply_project_regeneration(request, settings)
    assert not list(outside.iterdir())


def test_apply_preserves_git_worktree_metadata_file(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    (project / ".git").write_text("gitdir: /unchanged/worktree/metadata\n")
    request = _approved_request(project, settings)
    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=_regeneration_runner
    )
    assert result.succeeded
    assert (project / ".git").read_text() == "gitdir: /unchanged/worktree/metadata\n"


def test_final_manifest_mismatch_restores_deletions_and_preserves_external_work(
    tmp_path: Path, monkeypatch
) -> None:
    from stm32cubemx_mcp import regeneration_apply

    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    before = snapshot_project(project, settings)
    replace = regeneration_apply._replace_file

    def replace_and_add_external_work(source, target):
        replace(source, target)
        if target.name == "main.c" and "files" not in source.parts:
            (project / "external.txt").write_text("preserve external work")

    monkeypatch.setattr(regeneration_apply, "_replace_file", replace_and_add_external_work)
    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=_regeneration_runner
    )
    assert not result.succeeded and result.rolled_back
    assert "applied project hash" in result.diagnostics[-1].message
    after = snapshot_project(project, settings)
    assert after.pop("external.txt")
    assert after == before
    assert (project / "external.txt").read_text() == "preserve external work"


def test_apply_refuses_file_directory_type_changes_before_any_writes(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))

    def change_type_runner(*args):
        result = _regeneration_runner(*args)
        stage = next(args[2].iterdir())
        main = stage / "Core/Src/main.c"
        main.unlink()
        main.mkdir()
        (main / "new.c").write_text("new file")
        return result

    request = _approved_request(project, settings, change_type_runner)
    before = snapshot_project(project, settings)
    with pytest.raises(ValueError, match="parent is not a directory"):
        apply_project_regeneration(
            request, settings, validator=_valid_validator, script_runner=change_type_runner
        )
    assert snapshot_project(project, settings) == before
    assert not list(project.glob(".cubemx-mcp-regeneration/backup-*"))


def test_apply_rejects_failed_generation_without_source_changes(tmp_path: Path) -> None:
    project = _cubeide_project(tmp_path)
    settings = Settings(allowed_roots=(tmp_path,))
    request = _approved_request(project, settings)
    before = snapshot_project(project, settings)

    def failed_runner(*args):
        return CubeMXProcessResult(succeeded=False, exit_code=1, duration_seconds=0.01)

    result = apply_project_regeneration(
        request, settings, validator=_valid_validator, script_runner=failed_runner
    )
    assert not result.succeeded
    assert snapshot_project(project, settings) == before
    assert result.backup_path is None
