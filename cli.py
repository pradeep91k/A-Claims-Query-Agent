%%writefile cli.py
"""
Day 8: Claims Query Agent - CLI Interface
Run this from your terminal (NOT Jupyter):
    python cli.py
Then type any question and press Enter.
Type 'quit' or 'exit' to stop.
"""

import asyncio, sys, json, os, re
import nest_asyncio
from groq import Groq
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

nest_asyncio.apply()
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"


def normalize_query(query: str) -> str:
    query = re.sub(
        r'\b(clm)?(\d{4,})\b',
        lambda m: f"CLM{m.group(2)}",
        query, flags=re.IGNORECASE
    )
    query = re.sub(
        r'\bm(\d{4,})\b',
        lambda m: f"M{m.group(1)}",
        query, flags=re.IGNORECASE
    )
    return query


def mcp_tools_to_groq_format(mcp_tools):
    return [{
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.inputSchema,
        }
    } for t in mcp_tools]


async def call_one_tool(session, groq_tools, messages, client):
    response = client.chat.completions.create(
        model=MODEL, messages=messages,
        tools=groq_tools, tool_choice="auto",
    )
    response_message = response.choices[0].message

    if not response_message.tool_calls:
        return None, None, response_message.content

    tool_call = response_message.tool_calls[0]
    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)

    mcp_result = await session.call_tool(tool_name, tool_args)
    raw_data = json.loads(mcp_result.content[0].text)

    if (tool_name == "get_denial_reason"
            and raw_data.get("found")
            and raw_data.get("denial_code")):
        messages[0]["content"] += (
            f"\n\nIMPORTANT: Official {raw_data['code_type']} "
            f"{raw_data['denial_code']} description: "
            f"'{raw_data['description']}'. Use this exact wording."
        )

    messages.append(response_message)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": mcp_result.content[0].text,
    })

    final = client.chat.completions.create(
        model=MODEL, messages=messages,
        tools=groq_tools, tool_choice="none",
    )
    return tool_name, tool_args, final.choices[0].message.content


async def run_agent(user_query: str, session, groq_tools, client):
    normalized = normalize_query(user_query)

    system_prompt = (
        "You are a healthcare claims assistant at a US BPO. "
        "Use tools to look up real data — never guess. "
        "Claim IDs start with CLM (e.g. CLM5001). "
        "Member IDs start with M (e.g. M1001). "
        "If no ID is provided, ask the user for it. "
        "Reply in 2-4 plain English sentences. No JSON. No lists."
    )

    parts = re.split(
        r'\band also\b|\band\b(?=.*\bif\b)',
        normalized, flags=re.IGNORECASE
    )
    parts = [p.strip() for p in parts if p.strip()]

    for part in parts:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": part}
        ]
        tool_name, tool_args, summary = await call_one_tool(
            session, groq_tools, messages, client
        )
        divider = "-" * 55
        print(f"\n{divider}")
        if tool_name:
            print(f"  Tool: {tool_name}({tool_args})")
            print(divider)
        for line in summary.strip().split("\n"):
            print(f"  {line}")
        print(f"{divider}\n")


async def main():
    client = Groq(api_key=GROQ_API_KEY)
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server.py"],
    )
    errlog = open("server_stderr.log", "w")

    print("\n" + "=" * 55)
    print("  Healthcare Claims Query Agent")
    print("  Powered by Groq + MCP")
    print("  Type 'quit' to exit")
    print("=" * 55)

    # Open ONE MCP session for the entire CLI session
    # This is more efficient than reconnecting on every query
    async with stdio_client(server_params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            groq_tools = mcp_tools_to_groq_format(mcp_tools)

            print("\n  MCP server connected.")
            print(f"  Tools loaded: {[t.name for t in mcp_tools]}\n")

            while True:
                try:
                    query = input("  You: ").strip()
                    if not query:
                        continue
                    if query.lower() in ("quit", "exit"):
                        print("\n  Goodbye.\n")
                        break
                    await run_agent(query, session, groq_tools, client)
                except KeyboardInterrupt:
                    print("\n\n  Session ended.\n")
                    break


if __name__ == "__main__":
    asyncio.run(main())
