import os
from pathlib import Path

import pytest

from stm32cubemx_mcp.settings import Settings


def test_defaults_to_current_working_directory(tmp_path: Path) -> None:
    settings = Settings.from_env({}, cwd=tmp_path)

    assert settings.allowed_roots == (tmp_path.resolve(),)


def test_environment_roots_use_os_path_separator(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    value = os.pathsep.join((str(first), str(second)))

    settings = Settings.from_env({"CUBEMX_MCP_ALLOWED_ROOTS": value}, cwd=tmp_path)

    assert settings.allowed_roots == (first.resolve(), second.resolve())


def test_environment_can_enable_unvalidated_apply(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {"CUBEMX_MCP_ALLOW_UNVALIDATED_APPLY": "true"},
        cwd=tmp_path,
    )

    assert settings.allow_unvalidated_apply


def test_path_outside_allowed_root_is_rejected(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.ioc"
    outside.touch()
    settings = Settings(allowed_roots=(allowed.resolve(),))

    with pytest.raises(PermissionError, match="outside configured allowed roots"):
        settings.resolve_allowed_path(outside)
