import pytest
from mcp import Client

from stm32cubemx_mcp.server import mcp


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_environment_tool_returns_structured_output() -> None:
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("cubemx_environment", {})

    assert not result.is_error
    assert result.structured_content is not None
    assert "operating_system" in result.structured_content
    assert "allowed_roots" in result.structured_content
