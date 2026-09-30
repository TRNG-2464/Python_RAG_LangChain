"""The warehouse MCP server. It's complete; this lab connects to it rather than changing it."""

import json
from pathlib import Path

from fastmcp import FastMCP

DATA_FILE = Path(__file__).parent.parent / "data" / "inventory.json"

mcp = FastMCP("warehouse")


@mcp.tool
def shipping_cost(weight_kg: float, express: bool = False) -> float:
    """Calculate the shipping cost in US dollars for a parcel.

    Args:
        weight_kg: The parcel's weight in kilograms.
        express: Whether to use next-day express shipping.
    """
    rate = 3.0 if express else 1.5
    return round(5 + rate * weight_kg, 2)


@mcp.tool
def check_stock(sku: str) -> str:
    """Look up a product's stock level and storage bin by its SKU.

    Args:
        sku: The product's SKU, e.g. 'WID-100'.
    """
    inventory = json.loads(DATA_FILE.read_text())
    item = inventory.get(sku.upper())
    if item is None:
        return f"Unknown SKU {sku}"
    return f"{item['name']}: {item['on_hand']} on hand in bin {item['bin']}"


if __name__ == "__main__":
    mcp.run(show_banner=False)
