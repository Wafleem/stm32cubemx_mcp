# Development and testing

Use ASD-STE100 Technical English for all user-facing text. The rule also applies
to tool descriptions and diagnostic messages. See `AGENTS.md` for the project
rules.

## Test pyramid

### Unit tests

Unit tests run without STM32 software installed. They cover path policy, IOC
parsing, semantic summaries, deterministic rendering, plan hashing, and command
construction for Windows and macOS.

### Contract tests

The MCP Python SDK can connect to the server in memory. Contract tests enumerate
tools, validate their generated schemas, call them, and confirm structured
results without starting a subprocess.

### CubeMX integration tests

These tests require an explicit `CUBEMX_MCP_CUBEMX_PATH` and an installed STM32
firmware package. They operate only in a temporary directory and check:

1. load a known STM32F4 fixture;
2. save it through CubeMX;
3. compare the semantic before/after state;
4. generate STM32CubeIDE or CMake output;
5. verify expected generated artifacts.

They are opt-in locally and should run on a controlled self-hosted CI runner,
because STM32 packages are large and installation/licensing must remain outside
ordinary unit CI.

Run the installed CubeMX integration test on Windows with:

```powershell
$env:CUBEMX_MCP_RUN_INTEGRATION = "1"
pytest tests/integration/test_real_cubemx.py -m integration
```

### Build tests

Generated STM32CubeIDE projects are built through the IDE's headless interface.
CMake projects use configure/build presets and a discovered ARM toolchain. Test
success requires both a zero exit code and expected ELF/map artifacts.

## Useful commands

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
```

Run an MCP host/inspector using the SDK's development command:

```bash
mcp dev src/stm32cubemx_mcp/server.py
```

## Contribution rules

- Keep CubeMX version differences inside adapters.
- Do not delete or normalize unknown `.ioc` keys.
- Every mutation must have a dry-run representation and stale-source check.
- Tests must not write to real user projects.
- Never emit child-process output directly to stdout in stdio mode.
