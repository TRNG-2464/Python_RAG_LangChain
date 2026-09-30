"""An MCP Client — follow the README and fill in each part."""

import asyncio
from pathlib import Path

from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

# The server script this client launches. Anchored to this file so it's found from any directory.
SERVER = Path(__file__).parent / "warehouse_server.py"

llm = ChatOllama(model="llama3.1", temperature=0)
SYSTEM_PROMPT = "You help warehouse staff. Use the tools; never guess a number."


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


async def main():
    async with MCPAdapter(SERVER) as adapter:
        # Everything below goes inside this block, indented to this level.

        # --- Part 1: list the server's tools ---
        banner("Part 1: list the server's tools")

        # --- Part 2: call a tool directly ---
        banner("Part 2: call a tool directly")

        # --- Part 3: hand the tools to an agent ---
        banner("Part 3: hand the tools to an agent")

        # --- Part 4: find the tool call in the messages ---
        banner("Part 4: find the tool call in the messages")

        # --- Part 5: add a local tool ---
        banner("Part 5: add a local tool")


asyncio.run(main())
