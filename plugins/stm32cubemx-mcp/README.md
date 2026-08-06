# STM32CubeMX MCP for Codex

This unofficial plugin connects Codex to the local `stm32cubemx-mcp` server.
The plugin does not contain STM32CubeMX. Install STM32CubeMX and the Python MCP
package before you enable the plugin.

## Installation

Install the Python MCP command:

```powershell
pipx install git+https://github.com/Wafleem/stm32cubemx_mcp.git
```

The Windows launcher checks the Codex process PATH first. It then checks the
default pipx application path at
`%USERPROFILE%\.local\bin\stm32cubemx-mcp.exe`. Thus, the plugin can start the
server when the Codex desktop app has an older PATH value.

Add the marketplace and plugin:

```powershell
codex plugin marketplace add Wafleem/stm32cubemx_mcp
codex plugin add stm32cubemx-mcp@wafleem-stm32
```

Start a new Codex task. Use `/mcp` to check the `stm32cubemx` connection.

The automatic plugin launcher currently supports Windows. macOS support is a
planned platform checkpoint.

## Development installation

From the root of the `stm32cubemx-mcp` repository, install the Python command
in an isolated application environment:

```powershell
pipx install --editable .
```

Confirm that the command is available:

```powershell
stm32cubemx-mcp
```

The command waits for MCP protocol input. Stop it after you confirm that it
starts without an import error.

Start Codex from the embedded project directory. If
`CUBEMX_MCP_ALLOWED_ROOTS` is not set, the server restricts file access to its
current working directory.

## Tool use

Ask Codex to inspect the environment and the IOC file before it plans a change.
Review each change plan before you permit an apply or generation tool.

The current plugin can preview regeneration of an existing STM32CubeIDE
project. It cannot apply that regeneration plan yet.

## Status

This package is an unofficial development integration. It uses the MIT license.
