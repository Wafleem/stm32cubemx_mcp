import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
CODEX_PLUGIN = ROOT / "plugins" / "stm32cubemx-mcp"
CLAUDE_PLUGIN = ROOT / "integrations" / "claude" / "stm32cubemx-mcp"
CODEX_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_codex_plugin_registers_windows_pipx_launcher() -> None:
    manifest = _json(CODEX_PLUGIN / ".codex-plugin" / "plugin.json")
    mcp_config = _json(CODEX_PLUGIN / ".mcp.json")
    server = mcp_config["mcpServers"]["stm32cubemx"]

    assert manifest["name"] == "stm32cubemx-mcp"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert server["command"] == "powershell.exe"
    assert server["args"][:4] == [
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert ".local\\bin\\stm32cubemx-mcp.exe" in server["args"][4]
    assert server["env"]["CUBEMX_MCP_CUBEMX_TIMEOUT_SECONDS"] == "240"
    assert (CODEX_PLUGIN / "LICENSE").is_file()
    assert (CODEX_PLUGIN / "skills" / "configure-stm32cubemx" / "SKILL.md").is_file()


def test_codex_marketplace_points_to_plugin_package() -> None:
    marketplace = _json(CODEX_MARKETPLACE)
    entry = marketplace["plugins"][0]

    assert marketplace["name"] == "wafleem-stm32"
    assert entry["name"] == "stm32cubemx-mcp"
    assert entry["source"] == {
        "source": "local",
        "path": "./plugins/stm32cubemx-mcp",
    }
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }


def test_python_package_supplies_plugin_command() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"]["stm32cubemx-mcp"] == ("stm32cubemx_mcp.server:main")


def test_claude_plugin_registers_installed_mcp_command() -> None:
    manifest = _json(CLAUDE_PLUGIN / ".claude-plugin" / "plugin.json")
    mcp_config = _json(CLAUDE_PLUGIN / ".mcp.json")

    assert manifest["name"] == "stm32cubemx-mcp"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["userConfig"]["allowed_root"]["type"] == "directory"
    server = mcp_config["mcpServers"]["stm32cubemx"]
    assert server["command"] == "stm32cubemx-mcp"
    assert server["env"]["CUBEMX_MCP_ALLOWED_ROOTS"] == "${user_config.allowed_root}"
    assert (CLAUDE_PLUGIN / "LICENSE").is_file()
