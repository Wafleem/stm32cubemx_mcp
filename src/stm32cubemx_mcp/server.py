from __future__ import annotations

from mcp.server import MCPServer

from stm32cubemx_mcp.discovery import discover_environment
from stm32cubemx_mcp.ioc import inspect_ioc, list_ioc_files
from stm32cubemx_mcp.models import (
    EnvironmentReport,
    IocChangePlan,
    IocInspection,
    IocListResult,
    IocPlanRequest,
)
from stm32cubemx_mcp.planning import plan_ioc_changes
from stm32cubemx_mcp.settings import Settings

mcp = MCPServer(
    "stm32cubemx",
    instructions=(
        "Use this server as the deterministic STM32CubeMX execution layer. "
        "Interpret datasheets and schematics in the host agent, inspect the environment and IOC "
        "state first, and never claim that generation or a build occurred from inspection alone."
    ),
)


def _settings() -> Settings:
    return Settings.from_env()


@mcp.tool()
def cubemx_environment() -> EnvironmentReport:
    """Discover local STM32CubeMX, STM32CubeIDE, CMake, and related runtime state."""
    return discover_environment(_settings())


@mcp.tool()
def cubemx_list_ioc(
    root: str = ".",
    recursive: bool = True,
    limit: int = 100,
) -> IocListResult:
    """List IOC files below an allowed project directory without modifying them."""
    return list_ioc_files(root, _settings(), recursive=recursive, limit=limit)


@mcp.tool()
def cubemx_inspect_ioc(path: str) -> IocInspection:
    """Inspect one IOC file and return structured project, MCU, peripheral, pin, and clock data."""
    return inspect_ioc(path, _settings())


@mcp.tool()
def cubemx_plan_ioc_changes(request: IocPlanRequest) -> IocChangePlan:
    """Plan pin, peripheral, parameter, and project changes. Do not write a file."""
    return plan_ioc_changes(request, _settings())


def main() -> None:
    """Run the local stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
