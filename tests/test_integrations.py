import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
CODEX_PLUGIN = ROOT / "integrations" / "codex" / "stm32cubemx-mcp"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_codex_plugin_registers_installed_mcp_command() -> None:
    manifest = _json(CODEX_PLUGIN / ".codex-plugin" / "plugin.json")
    mcp_config = _json(CODEX_PLUGIN / ".mcp.json")

    assert manifest["name"] == "stm32cubemx-mcp"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert mcp_config["mcpServers"]["stm32cubemx"]["command"] == "stm32cubemx-mcp"
    assert (CODEX_PLUGIN / "LICENSE").is_file()


def test_python_package_supplies_plugin_command() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"]["stm32cubemx-mcp"] == ("stm32cubemx_mcp.server:main")
