import pytest
from mcp import Client

from stm32cubemx_mcp.server import mcp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_environment_tool_returns_structured_output() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        tool_list = await client.list_tools()
        result = await client.call_tool("cubemx_environment", {})

    tool_names = {tool.name for tool in tool_list.tools}
    assert "cubemx_environment" in tool_names
    assert "cubemx_list_ioc" in tool_names
    assert "cubemx_inspect_ioc" in tool_names
    assert "cubemx_plan_ioc_changes" in tool_names
    assert not result.is_error
    assert result.structured_content is not None
    assert "operating_system" in result.structured_content
    assert "allowed_roots" in result.structured_content
