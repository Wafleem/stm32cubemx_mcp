from __future__ import annotations

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from stm32cubemx_mcp.cubemx import ScriptRunner, run_cubemx_script, validate_ioc_content
from stm32cubemx_mcp.generation import ContentValidator
from stm32cubemx_mcp.models import (
    Diagnostic,
    ProjectFileChange,
    RegenerationApplyRequest,
    RegenerationApplyResult,
)
from stm32cubemx_mcp.regeneration import (
    REGENERATION_STATE_DIRECTORY,
    _file_sha256,
    _is_reparse_point,
    _manifest_sha256,
    _plan_project_regeneration,
    snapshot_project,
)
from stm32cubemx_mcp.settings import Settings


def _checked_path(root: Path, relative: str) -> Path:
    """Reject links and file/directory conflicts before each file operation."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise ValueError(f"Invalid project path: {relative}")
    current = root
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink() or (current.exists() and _is_reparse_point(current)):
            raise ValueError(f"Project path contains a link or reparse point: {current}")
        if current.exists():
            if index < len(parts) - 1 and not current.is_dir():
                raise ValueError(f"Project parent is not a directory: {current}")
            if index == len(parts) - 1 and not current.is_file():
                raise ValueError(f"Project file path is not a regular file: {current}")
    return current


def _current_hash(root: Path, relative: str) -> str | None:
    path = _checked_path(root, relative)
    return _file_sha256(path) if path.exists() else None


def _replace_file(source: Path, destination: Path) -> None:
    """Copy one file through a temporary file on the destination filesystem."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, stream)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copystat(source, temporary)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _project_lock(project: Path):
    state = project / REGENERATION_STATE_DIRECTORY
    if state.is_symlink() or (state.exists() and _is_reparse_point(state)):
        raise ValueError("The regeneration state directory cannot be a link or reparse point.")
    state.mkdir(exist_ok=True)
    lock = state / "apply.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ValueError(
            "A regeneration lock exists. Check for an active or interrupted apply before retrying."
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid()}, stream)
        yield state
    finally:
        lock.unlink(missing_ok=True)


def _rollback(project: Path, backup: Path, attempted: list[ProjectFileChange]) -> list[str]:
    conflicts: list[str] = []
    for change in reversed(attempted):
        try:
            current = _current_hash(project, change.path)
            if current == change.before_sha256:
                continue
            if current != change.after_sha256:
                conflicts.append(change.path)
                continue
            target = _checked_path(project, change.path)
            if change.before_sha256 is None:
                target.unlink(missing_ok=True)
            else:
                original = _checked_path(backup / "files", change.path)
                if _file_sha256(original) != change.before_sha256:
                    raise OSError("The backup hash changed.")
                _replace_file(original, target)
                if _current_hash(project, change.path) != change.before_sha256:
                    raise OSError("The restored file hash does not match.")
        except (OSError, ValueError):
            conflicts.append(change.path)
    return conflicts


def apply_project_regeneration(
    request: RegenerationApplyRequest,
    settings: Settings,
    *,
    validator: ContentValidator = validate_ioc_content,
    script_runner: ScriptRunner = run_cubemx_script,
) -> RegenerationApplyResult:
    """Recreate an approved preview and apply its exact file changes with backups."""
    project = settings.resolve_allowed_path(request.plan_request.project_directory)
    if not project.is_dir():
        raise ValueError("The project path is not a directory.")
    if _manifest_sha256(snapshot_project(project, settings)) != (
        request.expected_source_manifest_sha256
    ):
        raise ValueError("The source project changed. Create and approve a new regeneration plan.")

    with (
        _project_lock(project) as state,
        tempfile.TemporaryDirectory(prefix="cubemx-regeneration-apply-") as temporary,
    ):
        staged = Path(temporary) / "project"
        plan = _plan_project_regeneration(
            request.plan_request,
            settings,
            validator=validator,
            script_runner=script_runner,
            staged_output=staged,
        )
        result = RegenerationApplyResult(
            succeeded=False,
            project_path=str(project),
            plan_id=plan.plan_id,
            source_manifest_sha256=plan.source_manifest_sha256,
            changes=plan.changes,
            validation=plan.validation,
            cubemx=plan.cubemx,
            diagnostics=[
                item for item in plan.diagnostics if item.code != "regeneration.preview_only"
            ],
        )
        if not plan.succeeded:
            return result
        if (
            plan.source_manifest_sha256 != request.expected_source_manifest_sha256
            or plan.planned_manifest_sha256 != request.expected_planned_manifest_sha256
            or plan.plan_id != request.expected_plan_id
        ):
            raise ValueError("Regeneration differs from the approved plan. Create a new preview.")
        if _manifest_sha256(snapshot_project(staged, settings)) != plan.planned_manifest_sha256:
            raise ValueError("The staged project does not match the regeneration plan.")

        # Preflight all paths. File/directory type changes require a separate manual change.
        for change in plan.changes:
            if _current_hash(project, change.path) != change.before_sha256:
                raise ValueError(f"The source file changed: {change.path}")
        if _manifest_sha256(snapshot_project(project, settings)) != plan.source_manifest_sha256:
            raise ValueError("The source project changed before apply. Create a new preview.")
        if not plan.changes:
            return result.model_copy(
                update={"succeeded": True, "applied_manifest_sha256": plan.source_manifest_sha256}
            )

        backup = Path(tempfile.mkdtemp(prefix="backup-", dir=state))
        result.backup_path = str(backup)
        for change in plan.changes:
            if change.before_sha256 is not None:
                source = _checked_path(project, change.path)
                target = backup / "files" / change.path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                if _file_sha256(target) != change.before_sha256:
                    raise ValueError(f"The source changed during backup: {change.path}")
        (backup / "transaction.json").write_text(
            json.dumps(
                {
                    "request": request.model_dump(),
                    "changes": [change.model_dump() for change in plan.changes],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if _manifest_sha256(snapshot_project(project, settings)) != plan.source_manifest_sha256:
            raise ValueError("The source project changed during backup. Create a new preview.")

        attempted: list[ProjectFileChange] = []
        try:
            for change in plan.changes:
                if _current_hash(project, change.path) != change.before_sha256:
                    raise ValueError(f"The source file changed during apply: {change.path}")
                target = _checked_path(project, change.path)
                attempted.append(change)
                if change.after_sha256 is None:
                    target.unlink()
                else:
                    _replace_file(_checked_path(staged, change.path), target)
            applied = _manifest_sha256(snapshot_project(project, settings))
            if applied != plan.planned_manifest_sha256:
                raise OSError("The applied project hash does not match the approved plan.")
        except (OSError, ValueError) as error:
            conflicts = _rollback(project, backup, attempted)
            result.rolled_back = not conflicts
            result.recovery_required = bool(conflicts)
            result.changed = bool(conflicts)
            result.diagnostics.append(
                Diagnostic(severity="error", code="regeneration.apply_failed", message=str(error))
            )
            if conflicts:
                result.diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="regeneration.recovery_required",
                        message="Restore these paths from the backup after review: "
                        + ", ".join(conflicts),
                    )
                )
            return result
        return result.model_copy(
            update={
                "succeeded": True,
                "changed": True,
                "applied_manifest_sha256": applied,
            }
        )
