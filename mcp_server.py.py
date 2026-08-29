%%writefile mcp_server.py
from mcp.server.fastmcp import FastMCP
import tools

mcp = FastMCP("claims-query-agent")

@mcp.tool()
def check_claim_status(claim_id: str) -> dict:
    """Look up the current status of a healthcare claim by its claim ID.
    Args:
        claim_id: The claim identifier, e.g. 'CLM5001'.
    """
    return tools.check_claim_status(claim_id)

@mcp.tool()
def check_eligibility(member_id: str) -> dict:
    """Look up coverage and eligibility status for a health plan member.
    Args:
        member_id: The member identifier, e.g. 'M1001'.
    """
    return tools.check_eligibility(member_id)

@mcp.tool()
def get_denial_reason(claim_id: str) -> dict:
    """Look up why a claim was denied, including CARC/RARC code and description.
    Args:
        claim_id: The claim identifier, e.g. 'CLM5001'.
    """
    return tools.get_denial_reason(claim_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")

%%writefile test_client.py
import asyncio, sys, nest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
nest_asyncio.apply()

async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server.py"],
    )
    errlog = open("server_stderr.log", "w")
    async with stdio_client(server_params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=== Tools discovered ===")
            tools_response = await session.list_tools()
            for t in tools_response.tools:
                print(f"- {t.name}")

            print("\n=== check_claim_status('CLM5001') ===")
            result = await session.call_tool("check_claim_status", {"claim_id": "CLM5001"})
            print(result.content[0].text)

            print("\n=== check_eligibility('M1001') ===")
            result = await session.call_tool("check_eligibility", {"member_id": "M1001"})
            print(result.content[0].text)

            print("\n=== get_denial_reason('CLM5001') ===")
            result = await session.call_tool("get_denial_reason", {"claim_id": "CLM5001"})
            print(result.content[0].text)

asyncio.run(main())
