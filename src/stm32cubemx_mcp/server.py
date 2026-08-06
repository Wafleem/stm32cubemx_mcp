from __future__ import annotations

from mcp.server import MCPServer

from stm32cubemx_mcp.apply import apply_ioc_changes
from stm32cubemx_mcp.cubemx import validate_ioc_file
from stm32cubemx_mcp.discovery import discover_environment
from stm32cubemx_mcp.generation import generate_project
from stm32cubemx_mcp.ioc import inspect_ioc, list_ioc_files
from stm32cubemx_mcp.models import (
    EnvironmentReport,
    IocApplyRequest,
    IocApplyResult,
    IocChangePlan,
    IocInspection,
    IocListResult,
    IocPlanRequest,
    IocValidationResult,
    ProjectGenerationRequest,
    ProjectGenerationResult,
)
from stm32cubemx_mcp.planning import plan_ioc_changes
from stm32cubemx_mcp.settings import Settings

mcp = MCPServer(
    "stm32cubemx",
    instructions=(
        "Use this server as the deterministic STM32CubeMX execution layer. "
        "The host agent must analyze datasheets and schematics. "
        "Inspect the environment and the IOC state first. "
        "Do not report generation or build success after an inspection."
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


@mcp.tool()
def cubemx_apply_ioc_changes(request: IocApplyRequest) -> IocApplyResult:
    """Apply an approved IOC plan. Create a backup and replace the source file."""
    return apply_ioc_changes(request, _settings())


@mcp.tool()
def cubemx_validate_ioc(path: str) -> IocValidationResult:
    """Load and save an IOC copy with STM32CubeMX. Do not change the source file."""
    return validate_ioc_file(path, _settings())


@mcp.tool()
def cubemx_generate_project(request: ProjectGenerationRequest) -> ProjectGenerationResult:
    """Generate one new STM32CubeIDE project in a new output directory."""
    return generate_project(request, _settings())


def main() -> None:
    """Run the local stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
