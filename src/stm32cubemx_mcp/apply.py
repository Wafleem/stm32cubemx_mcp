from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

from stm32cubemx_mcp.models import IocApplyRequest, IocApplyResult
from stm32cubemx_mcp.planning import prepare_ioc_changes
from stm32cubemx_mcp.settings import Settings


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_backup(path: Path, source_sha256: str) -> Path:
    backup = path.with_name(f"{path.name}.bak.{source_sha256[:12]}")
    if backup.exists():
        if _sha256(backup) != source_sha256:
            raise FileExistsError(f"Backup path has different content: {backup}")
        return backup
    shutil.copy2(path, backup)
    return backup


def _atomic_replace(path: Path, content: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def apply_ioc_changes(request: IocApplyRequest, settings: Settings) -> IocApplyResult:
    """Apply an approved IOC plan with a backup and an atomic replacement."""
    plan, content = prepare_ioc_changes(request.plan_request, settings)
    expected = request.expected_source_sha256.lower()
    if plan.source_sha256 != expected:
        raise ValueError(
            "The IOC source hash changed. Create and approve a new change plan before apply."
        )

    path = Path(plan.path)
    if not plan.changes:
        return IocApplyResult(
            plan_id=plan.plan_id,
            path=plan.path,
            source_sha256=plan.source_sha256,
            applied_sha256=plan.source_sha256,
            changed=False,
        )

    backup = _create_backup(path, plan.source_sha256)
    _atomic_replace(path, content)
    applied_sha256 = _sha256(path)
    if applied_sha256 != plan.planned_sha256:
        raise OSError("The applied IOC hash is not equal to the approved plan hash.")

    return IocApplyResult(
        plan_id=plan.plan_id,
        path=plan.path,
        backup_path=str(backup),
        source_sha256=plan.source_sha256,
        applied_sha256=applied_sha256,
        changed=True,
        changed_keys=[change.key for change in plan.changes],
    )
