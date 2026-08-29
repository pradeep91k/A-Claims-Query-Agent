from dotenv import load_dotenv
import os
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

%%writefile agent.py
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


def format_output(query, tool_name, tool_args, summary):
    divider = "=" * 55
    print(f"\n{divider}")
    print(f"  Query : {query}")
    print(f"  Tool  : {tool_name}({tool_args})")
    print(f"{divider}")
    for line in summary.strip().split("\n"):
        print(f"  {line}")
    print(f"{divider}\n")


async def call_one_tool(session, groq_tools, messages, client):
    """
    One round of: Groq picks tool → MCP runs it → Groq summarizes.
    Returns the plain English summary string.
    Handles the case where Groq tries to make a second tool call
    instead of summarizing — forces a plain text response.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=groq_tools,
        tool_choice="auto",
    )
    response_message = response.choices[0].message

    # Groq answered directly without a tool
    if not response_message.tool_calls:
        return None, None, None, response_message.content

    tool_call = response_message.tool_calls[0]
    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)

    mcp_result = await session.call_tool(tool_name, tool_args)
    raw_data = json.loads(mcp_result.content[0].text)

    # Inject real CARC/RARC description to prevent hallucination
    if (tool_name == "get_denial_reason"
            and raw_data.get("found")
            and raw_data.get("denial_code")):
        messages[0]["content"] += (
            f"\n\nIMPORTANT: The official {raw_data['code_type']} "
            f"{raw_data['denial_code']} description is: "
            f"'{raw_data['description']}'. Use this exact wording."
        )

    messages.append(response_message)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": mcp_result.content[0].text,
    })

    # Force plain text summary — no more tool calls
    final = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=groq_tools,
        tool_choice="none",   # KEY FIX: blocks Groq from making a 2nd tool call
    )
    summary = final.choices[0].message.content
    return tool_name, tool_args, raw_data, summary


async def run_agent(user_query: str):
    client = Groq(api_key=GROQ_API_KEY)

    normalized = normalize_query(user_query)
    if normalized != user_query:
        print(f"\n  [Normalized: '{user_query}' → '{normalized}']")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_server.py"],
    )
    errlog = open("server_stderr.log", "w")

    try:
        async with stdio_client(server_params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                mcp_tools = (await session.list_tools()).tools
                groq_tools = mcp_tools_to_groq_format(mcp_tools)

                system_prompt = (
                    "You are a healthcare claims assistant at a US BPO. "
                    "Use tools to look up real data — never guess. "
                    "Claim IDs start with CLM (e.g. CLM5001). "
                    "Member IDs start with M (e.g. M1001). "
                    "If no ID is provided, ask the user for it. "
                    "Reply in 2-4 plain English sentences. No JSON. No lists."
                )

                # Handle multi-part queries by splitting on 'and also'
                # Each part runs as a separate tool call in the same MCP session
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
                    tool_name, tool_args, _, summary = await call_one_tool(
                        session, groq_tools, messages, client
                    )
                    if tool_name:
                        format_output(part, tool_name, tool_args, summary)
                    else:
                        divider = "=" * 55
                        print(f"\n{divider}")
                        print(f"  Query : {part}")
                        print(f"{divider}")
                        print(f"  {summary}")
                        print(f"{divider}\n")

    except Exception as e:
        divider = "=" * 55
        print(f"\n{divider}")
        print(f"  Query : {user_query}")
        print(f"  Error : {type(e).__name__} — {str(e)[:120]}")
        print(f"{divider}\n")


# Day 7 final edge case tests
queries = [
    "Check claim 5001",
    "What is status of claim clm5001",
    "Is member M9999 eligible?",
    "Why was my claim denied?",
    "Check claim CLM5001 and also tell me if member M1001 is covered",
]

for q in queries:
    asyncio.run(run_agent(q))
