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
