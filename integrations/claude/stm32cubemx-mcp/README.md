# STM32CubeMX MCP for Claude Code

This unofficial plugin connects Claude Code to the local `stm32cubemx-mcp`
server. The plugin does not contain STM32CubeMX. Install STM32CubeMX and the
Python MCP package before you enable the plugin.

## Development installation

From the root of the `stm32cubemx-mcp` repository, install the Python command:

```powershell
pipx install --editable .
```

Test the plugin from the repository:

```powershell
claude --plugin-dir .\integrations\claude\stm32cubemx-mcp
```

Claude Code asks for the allowed STM32 project directory. The MCP rejects file
paths outside this directory.

Use `/mcp` to confirm that the `stm32cubemx` server is connected. Use
`/reload-plugins` after you change the plugin files.

## Tool use

Ask Claude to inspect the environment and the IOC file before it plans a
change. Review each plan before you permit an apply or generation tool.

The current plugin can preview regeneration of an existing STM32CubeIDE
project. It cannot apply that regeneration plan yet.

## Status

This package is an unofficial development integration. It uses the MIT license.
