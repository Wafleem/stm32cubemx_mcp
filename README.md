# STM32CubeMX MCP

`stm32cubemx-mcp` is a local Model Context Protocol (MCP) server. It helps
artificial intelligence (AI) agents turn structured embedded-system
requirements into safe, testable STM32CubeMX workflows.

Project documentation and user-facing text use ASD-STE100 Technical English.

The agent analyzes microcontroller unit (MCU) datasheets, schematics, board
photos, and user requirements.
This server supplies the deterministic execution layer. It inspects the local
toolchain and `.ioc` files. It validates paths and configuration state. It will
also control CubeMX validation and project generation.

> [!IMPORTANT]
> The project is in early development. The current tools inspect, plan,
> validate, create, and apply `.ioc` changes. The tools can generate a new
> STM32CubeIDE project. They can also preview regeneration of an existing
> project. CMake output and builds are the next implementation milestones.

## Current MCP tools

Tool | Purpose | File effect
--- | --- | ---
`cubemx_environment` | Find CubeMX, CubeIDE, Python, CMake, and Ninja. | Read-only
`cubemx_list_ioc` | Find IOC files below an allowed directory. | Read-only
`cubemx_inspect_ioc` | Read MCU, project, peripheral, pin, clock, and version data. | Read-only
`cubemx_plan_ioc_changes` | Preview pin, peripheral, parameter, and project changes. | Read-only
`cubemx_apply_ioc_changes` | Validate and apply an approved IOC plan. | Creates a backup and replaces one IOC file
`cubemx_validate_ioc` | Load and save a staged IOC copy with CubeMX. | Source file remains unchanged
`cubemx_create_ioc` | Create and validate one IOC file for a board or MCU. | Creates one new directory
`cubemx_generate_project` | Generate one new STM32CubeIDE project. | Creates one new output container
`cubemx_plan_regeneration` | Regenerate a temporary copy of an existing CubeIDE project. | Source project remains unchanged

## Intended workflow

```mermaid
flowchart LR
    A["User inputs: requirements, datasheets, schematics"] --> B["AI agent: hardware intent"]
    B --> C["MCP: inspect and resolve constraints"]
    C --> D["MCP: plan and preview IOC changes"]
    D --> E["MCP: transactional apply"]
    E --> F["CubeMX CLI: validate and generate"]
    F --> G["CubeIDE or CMake: build"]
    G --> H["Structured diagnostics for the agent"]
```

The supported CubeMX command-line interface (CLI) loads MCUs, boards, and
`.ioc` configurations. It can generate STM32CubeIDE or CMake projects. It does
not expose the complete
pin/peripheral editor as a command API. For that reason, this project treats
`.ioc` changes as version-aware transactions and uses CubeMX as the validation
and generation authority.

See [Architecture](docs/architecture.md) for the safety model and planned tool
contract.

## Codex plugin

This repository is an unofficial Codex plugin marketplace. The plugin contains
the Codex workflow guidance and the MCP server configuration. The Python
package contains the executable MCP server.

### Install on Windows

Install the Codex CLI if `codex.cmd --version` does not work:

```powershell
npm.cmd install --global @openai/codex
```

Install `pipx` if `py -m pipx --version` does not work:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Install the Python MCP server:

```powershell
py -m pipx install git+https://github.com/Wafleem/stm32cubemx_mcp.git
```

The Windows plugin first searches the Codex process PATH. If the command is not
on that PATH, the plugin uses the default pipx application path at
`%USERPROFILE%\.local\bin\stm32cubemx-mcp.exe`. This fallback lets the Codex
desktop app start the server after `pipx` changes the user PATH.

Add the marketplace and install the plugin:

```powershell
codex.cmd plugin marketplace add Wafleem/stm32cubemx_mcp
codex.cmd plugin add stm32cubemx-mcp@wafleem-stm32
```

Close Codex after the installation. Open Codex again and start a new task. Use
`/mcp` to confirm that the `stm32cubemx` server is connected. The plugin source
is in [`plugins/stm32cubemx-mcp`](plugins/stm32cubemx-mcp).

### Verify the installation

Run these checks in a new PowerShell window:

```powershell
Get-Command stm32cubemx-mcp
py -m pipx list
codex.cmd --version
codex.cmd plugin list
```

The `stm32cubemx-mcp` command starts a standard-input MCP server. It waits for
MCP messages. This wait is correct. Press `Ctrl+C` if you start the server
manually. Do not use a manual server start as the connection test.

Use this prompt in a new Codex task for a read-only connection test:

```text
Use the installed STM32CubeMX plugin. Call cubemx_environment. Do not modify
files. Report the CubeMX path, Java path, operating system, allowed roots, and
diagnostics.
```

### Update the installation

Update the Python server when a runtime release is available:

```powershell
py -m pipx upgrade stm32cubemx-mcp
```

Refresh the marketplace and reinstall the current plugin version:

```powershell
codex.cmd plugin marketplace upgrade wafleem-stm32
codex.cmd plugin add stm32cubemx-mcp@wafleem-stm32
```

Close Codex and start a new task after the update.

## Usage guide

### 1. Give the technical evidence to the agent

Attach the datasheet, schematic, board image, IOC file, and project files to
the Codex task as applicable. State the MCU part number and package. State the
required peripheral, signal, data rate, clock, and pin restrictions.

Codex analyzes this evidence. The MCP server does not read or interpret the
datasheet or schematic by itself. Codex converts the result of its analysis
into structured MCP tool calls.

Example request:

```text
This project uses an STM32F401RE on a NUCLEO-F401RE. Configure USART2 for
115200 bit/s on PA2 and PA3. Preserve the Serial Wire Debug (SWD) pins. Inspect
and plan the change. Do not modify the IOC file until I approve the plan.
```

### 2. Create or inspect the IOC file

Codex first calls `cubemx_environment`. It confirms the CubeMX path and the
allowed roots.

For a new project, Codex can call `cubemx_create_ioc`. The call selects one
known board or microcontroller unit (MCU). It selects the project name,
toolchain, and a new output directory. The server uses typed CubeMX commands.
It validates the new IOC file before it makes the output directory available.

For an existing project, Codex can call `cubemx_list_ioc` if the IOC path is
not known. It then calls `cubemx_inspect_ioc` to read the current project
state.

The inspection result includes the source SHA-256 hash. This hash identifies
the exact IOC content that Codex inspected.

### 3. Create and review a change plan

Codex calls `cubemx_plan_ioc_changes`. This tool returns:

- a plan identifier;
- the source and planned SHA-256 hashes;
- a list of changed IOC keys;
- a unified text difference;
- diagnostics.

This call does not write the IOC file. Review the pin assignments, peripheral
names, parameter values, project name, and toolchain. Give approval only for
the displayed plan.

### 4. Apply an approved IOC plan

After approval, Codex calls `cubemx_apply_ioc_changes` with the same plan
request and the approved source hash. The server creates the plan again. It
stops if the source hash changed.

By default, the server validates the planned IOC content with CubeMX before it
writes the source file. It then creates a hash-named backup and uses one atomic
replacement operation. It restores the backup if the applied hash is not equal
to the approved planned hash.

Do not disable CubeMX validation for normal use. The validation bypass requires
both an explicit request value and the
`CUBEMX_MCP_ALLOW_UNVALIDATED_APPLY=true` server setting.

### 5. Generate or preview a project

Use `cubemx_generate_project` for a new STM32CubeIDE project. The output
directory must not exist. The tool validates the IOC file, generates into a
temporary directory, and then checks the complete CubeIDE output. The check
resolves each linked resource in the Eclipse `.project` file. It also requires
`main.c`, `main.h`, a CMSIS core header, and a Hardware Abstraction Layer (HAL)
source file. The tool moves the complete output container to the requested
path only after these checks pass.

The tool sets the staged IOC project name and filename to the requested project
name. It selects the current CubeMX toolchain key when that key is available.
It also requests a project below one root directory. These staged changes do
not change the source IOC file.

The `output_directory` result identifies the complete generated container. The
`project_path` result identifies the Eclipse project root. These paths are
usually equal. They can be different when CubeMX creates nested Eclipse
metadata.

Use `cubemx_plan_regeneration` for an existing STM32CubeIDE project. This tool
copies the project before validation. It validates the IOC file in an isolated
temporary directory. It then regenerates the copy and reports added, modified,
and deleted files. It checks the source project after each phase. It does not
change the source project.

The current server does not apply an existing-project regeneration plan. It
also does not compile a project. Treat IOC validation, project generation, and
compilation as different results.

### 6. Use allowed roots

All input and output paths must be below an allowed root. If
`CUBEMX_MCP_ALLOWED_ROOTS` is not set, the server permits only its current
working directory. On Windows, separate multiple roots with a semicolon.

Example:

```powershell
$env:CUBEMX_MCP_ALLOWED_ROOTS = "C:\work\board-a;D:\shared\firmware"
```

This command applies to Codex processes that start from the same PowerShell
session. For the desktop app, set the variable in the Windows user environment
and then restart the app. Use `cubemx_environment` to confirm the effective
roots.

## MCP API and tool-call overview

The server uses MCP over standard input and standard output. It does not expose
an HTTP API. Codex and other MCP clients create the JSON-RPC messages. Most
users must use natural-language prompts instead of writing JSON-RPC messages.

All tool results use structured JSON. Diagnostics contain `severity`, `code`,
`message`, and an optional IOC line number.

CubeMX process results contain the exit code, duration, timeout state, and
captured output. Successful results contain only a short output tail. Failed
results keep a larger bounded output for diagnosis. Nonfatal Java preferences
output uses the `cubemx.java_preferences_warning` diagnostic code.

### Read-only calls

#### `cubemx_environment`

Arguments:

```json
{}
```

Main result fields: `operating_system`, `architecture`, `python_version`,
`python_executable`, `cubemx`, `cubeide`, `cmake`, `ninja`, `allowed_roots`, and
`diagnostics`.

#### `cubemx_list_ioc`

Arguments:

```json
{
  "root": ".",
  "recursive": true,
  "limit": 100
}
```

`root` defaults to the current directory. `recursive` defaults to `true`.
`limit` defaults to `100`. The result contains `root`, `files`, and
`truncated`.

#### `cubemx_inspect_ioc`

Arguments:

```json
{
  "path": "board.ioc"
}
```

The result contains `summary` and `diagnostics`. The summary contains MCU,
board, project, toolchain, CubeMX version, peripheral, pin, clock, file size,
and source-hash data.

#### `cubemx_validate_ioc`

Arguments:

```json
{
  "path": "board.ioc"
}
```

The result contains `valid`, source and round-trip hashes, the CubeMX process
result, and diagnostics. The source IOC file remains unchanged.

### IOC creation, plan, and apply calls

#### `cubemx_create_ioc`

The tool has one `request` argument:

```json
{
  "request": {
    "target_kind": "board",
    "target": "NUCLEO-F401RE",
    "output_directory": "projects/f401-base",
    "project_name": "f401_base",
    "board_mode": "allmodes",
    "toolchain": "STM32CubeIDE"
  }
}
```

Set `target_kind` to `board` or `mcu`. Use the exact CubeMX board or MCU
identifier in `target`. `board_mode` can be `allmodes` or `nomode`. The
toolchain can be `STM32CubeIDE` or `CMake`. The output directory must not
exist.

The result contains the IOC path, project path, target, toolchain, source
hash, validation result, CubeMX process result, and diagnostics. The server
removes the staged directory if creation or validation fails.

#### `cubemx_plan_ioc_changes`

The tool has one `request` argument:

```json
{
  "request": {
    "path": "board.ioc",
    "pin_assignments": [
      {
        "pin": "PA2",
        "signal": "USART2_TX",
        "label": "DEBUG_TX",
        "locked": true
      },
      {
        "pin": "PA3",
        "signal": "USART2_RX",
        "label": "DEBUG_RX",
        "locked": true
      }
    ],
    "enabled_peripherals": ["USART2"],
    "parameter_updates": {},
    "project_name": null,
    "toolchain": "STM32CubeIDE",
    "allow_debug_pin_change": false
  }
}
```

Use exact CubeMX IOC keys in `parameter_updates`. Do not guess these keys. Use
`pin_assignments` for pin signals, labels, and lock states. The server rejects
these pin properties in `parameter_updates`. `toolchain` can be
`STM32CubeIDE`, `CMake`, or `null`. Debug-pin changes are blocked unless
`allow_debug_pin_change` is `true`.

The result contains `plan_id`, `source_sha256`, `planned_sha256`, `changes`,
`unified_diff`, `validation_status`, and `diagnostics`.

#### `cubemx_apply_ioc_changes`

The tool has one `request` argument. `plan_request` must be equal to the
approved planning request:

```json
{
  "request": {
    "plan_request": {
      "path": "board.ioc",
      "pin_assignments": [
        {
          "pin": "PA2",
          "signal": "USART2_TX",
          "label": "DEBUG_TX",
          "locked": true
        },
        {
          "pin": "PA3",
          "signal": "USART2_RX",
          "label": "DEBUG_RX",
          "locked": true
        }
      ],
      "enabled_peripherals": ["USART2"],
      "parameter_updates": {},
      "project_name": null,
      "toolchain": "STM32CubeIDE",
      "allow_debug_pin_change": false
    },
    "expected_source_sha256": "<64-character hash from the approved plan>",
    "skip_cubemx_validation": false
  }
}
```

The result contains the plan identifier, source and applied hashes, backup
path, change state, CubeMX validation state, and changed IOC keys.

### Project calls

#### `cubemx_generate_project`

The tool has one `request` argument:

```json
{
  "request": {
    "ioc_path": "board.ioc",
    "output_directory": "generated/blinky",
    "project_name": "blinky",
    "toolchain": "STM32CubeIDE"
  }
}
```

The current generation tool supports only `STM32CubeIDE`. The project name can
contain letters, numbers, `_`, `.`, and `-`. It can contain 1 to 80 characters.
The source IOC file remains unchanged. The result contains `succeeded`,
`output_directory`, `project_path`, `project_name`, `toolchain`,
`source_sha256`, the validation result, the CubeMX process result, the
generated-file list, and diagnostics. `output_directory` identifies the
complete output container. `project_path` identifies the Eclipse project root.

#### `cubemx_plan_regeneration`

The tool has one `request` argument:

```json
{
  "request": {
    "project_directory": "existing-project",
    "ioc_path": null
  }
}
```

Set `ioc_path` when the project contains more than one IOC file. A relative IOC
path is relative to `project_directory`. The result contains source and planned
project-manifest hashes, file changes, IOC validation, the CubeMX process
result, and diagnostics. Check `succeeded` before you use `plan_id` or
`planned_manifest_sha256`. These fields can be null when a safe preview does
not complete. A source-change diagnostic identifies each detected path.

### JSON-RPC call form

An MCP client sends a tool call in this form:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "cubemx_inspect_ioc",
    "arguments": {
      "path": "board.ioc"
    }
  }
}
```

The MCP client performs protocol initialization before it sends this call.
Application code should use an MCP SDK instead of writing protocol messages
directly.

## Requirements

- Python 3.11 or newer
- STM32CubeMX for generation and validation features
- STM32CubeIDE and/or a CMake ARM toolchain for build features

Windows is the first development platform. macOS on Apple silicon is a target
platform and is represented in the platform abstraction and CI matrix. The
current Codex plugin launcher supports Windows. macOS users must configure the
MCP executable path manually until the macOS plugin launcher is available.

## Development setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

On macOS:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Run the stdio server with:

```bash
stm32cubemx-mcp
```

MCP hosts should launch the server using an absolute Python or executable path.
Nothing except MCP protocol messages may be written to stdout; application logs
go to stderr.

## Configuration

Environment variable | Purpose
--- | ---
`CUBEMX_MCP_CUBEMX_PATH` | Explicit CubeMX launcher path
`CUBEMX_MCP_ALLOWED_ROOTS` | OS-path-separated project roots the MCP may read or change
`CUBEMX_MCP_MAX_IOC_BYTES` | Maximum `.ioc` size accepted; defaults to 5 MiB
`CUBEMX_MCP_MAX_PROJECT_FILES` | Maximum project file count; defaults to 20,000
`CUBEMX_MCP_MAX_PROJECT_BYTES` | Maximum project size; defaults to 500 MiB
`CUBEMX_MCP_CUBEMX_TIMEOUT_SECONDS` | Maximum CubeMX operation time; defaults to 120 seconds
`CUBEMX_MCP_ALLOW_UNVALIDATED_APPLY` | Permit an explicit validation bypass; defaults to false

When `CUBEMX_MCP_ALLOWED_ROOTS` is unset, access is restricted to the process's
current working directory. This default is deliberately narrow.

## References

- [STM32CubeMX 6.18 command-line documentation](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.0/en/docs/markup/CubeMX_CLI.html)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## License

MIT
