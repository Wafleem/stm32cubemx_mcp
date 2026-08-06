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
> The project is at an early scaffold stage. The current tools are read-only.
> Transactional `.ioc` planning, CubeMX validation, project generation, and
> builds are the next implementation milestones.

## Current MCP tools

- `cubemx_environment` discovers CubeMX, CubeIDE, Python, CMake, and Ninja.
- `cubemx_list_ioc` finds `.ioc` files beneath an allowed directory.
- `cubemx_inspect_ioc` returns structured MCU, project, peripheral, pin, clock,
  and version information without changing the file.

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

## Requirements

- Python 3.11 or newer
- STM32CubeMX for generation and validation features
- STM32CubeIDE and/or a CMake ARM toolchain for build features

Windows is the first development platform. macOS on Apple silicon is a target
platform and is represented in the platform abstraction and CI matrix.

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

When `CUBEMX_MCP_ALLOWED_ROOTS` is unset, access is restricted to the process's
current working directory. This default is deliberately narrow.

## References

- [STM32CubeMX 6.18 command-line documentation](https://dev.st.com/stm32cube-docs/stm32cubemx/6.18.0/en/docs/markup/CubeMX_CLI.html)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## License

MIT
