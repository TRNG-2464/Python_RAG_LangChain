"""An MCP Server — follow the README and fill in each part."""

import json
from pathlib import Path

from fastmcp import FastMCP

# Anchored to this file, so it resolves no matter which directory the server is launched from.
DATA_FILE = Path(__file__).parent.parent / "data" / "inventory.json"

mcp = FastMCP("warehouse")


# --- Part 1: a tool with typed parameters ---


# --- Part 5: a tool that reads the data file ---


if __name__ == "__main__":
    mcp.run()
