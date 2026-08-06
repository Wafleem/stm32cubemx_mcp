# STM32CubeMX MCP

`stm32cubemx-mcp` is a local Model Context Protocol server that helps AI agents
turn structured embedded-system requirements into safe, testable STM32CubeMX
workflows.

Project documentation and user-facing text use ASD-STE100 Technical English.

The agent analyzes datasheets, schematics, board photos, and user requirements.
This server supplies the deterministic execution layer. It inspects the local
toolchain and `.ioc` files. It validates paths and configuration state. It will
also control CubeMX generation and builds.

> [!IMPORTANT]
> The project is in early development. The current tools inspect, plan,
> validate, and apply `.ioc` changes. The tools can generate a new
> STM32CubeIDE project. They can also preview regeneration of an existing
> project. CMake output and builds are the next implementation milestones.

## Current MCP tools

- `cubemx_environment` discovers CubeMX, CubeIDE, Python, CMake, and Ninja.
- `cubemx_list_ioc` finds `.ioc` files beneath an allowed directory.
- `cubemx_inspect_ioc` returns structured MCU, project, peripheral, pin, clock,
  and version information without changing the file.
- `cubemx_plan_ioc_changes` previews pin, peripheral, parameter, and project
  changes. It returns a content hash and a unified text difference. It does not
  write the `.ioc` file.
- `cubemx_apply_ioc_changes` applies an approved plan. It checks the source
  hash. It creates a backup. It replaces the source file with one atomic
  operation.
- `cubemx_validate_ioc` runs a CubeMX load and save test on a staged copy. It
  checks the required IOC settings after the CubeMX save operation.
- `cubemx_generate_project` generates a new STM32CubeIDE project. It validates
  the source IOC file. It generates files in a temporary directory. It moves a
  complete project to a new output directory.
- `cubemx_plan_regeneration` regenerates a temporary copy of an existing
  STM32CubeIDE project. It returns added, modified, and deleted files. It does
  not change the source project.

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

CubeMX's supported CLI loads MCUs, boards, and `.ioc` configurations and can
generate STM32CubeIDE or CMake projects. It does not expose the complete
pin/peripheral editor as a command API. For that reason, this project treats
`.ioc` changes as version-aware transactions and uses CubeMX as the validation
and generation authority.

See [Architecture](docs/architecture.md) for the safety model and planned tool
contract.

## Codex plugin

This repository is an unofficial Codex plugin marketplace. Install the Python
MCP command first:

```powershell
pipx install git+https://github.com/Wafleem/stm32cubemx_mcp.git
```

The Windows plugin first searches the Codex process PATH. If the command is not
on that PATH, the plugin uses the default pipx application path at
`%USERPROFILE%\.local\bin\stm32cubemx-mcp.exe`. This fallback lets the Codex
desktop app start the server after `pipx` changes the user PATH.

Then add the marketplace and plugin:

```powershell
codex plugin marketplace add Wafleem/stm32cubemx_mcp
codex plugin add stm32cubemx-mcp@wafleem-stm32
```

Start a new Codex task after installation. Use `/mcp` to confirm that the
`stm32cubemx` server is connected. The plugin source is in
[`plugins/stm32cubemx-mcp`](plugins/stm32cubemx-mcp).

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
