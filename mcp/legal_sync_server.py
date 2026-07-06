"""MCP server for legal rule comparison against external sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:
    Server = None  # type: ignore[misc, assignment]


RULES_PATH = Path("config/rules/labor_law")


def load_yaml_rule(filename: str) -> dict[str, Any]:
    filepath = RULES_PATH / filename
    if not filepath.exists():
        return {}
    return yaml.safe_load(filepath.read_text(encoding="utf-8")) or {}


def compare_rules(local: dict[str, Any], external_description: str) -> dict[str, Any]:
    """Compare local YAML rules against external source description."""
    differences = []
    local_rules = local.get("rules", {})

    for rule_key, rule_data in local_rules.items():
        local_desc = rule_data.get("description", {}).get("he", "")
        if external_description and local_desc:
            differences.append({
                "rule_key": rule_key,
                "rule_id": rule_data.get("id"),
                "local_description": local_desc,
                "external_reference": external_description[:200],
                "status": "review_required",
            })

    return {
        "differences_found": len(differences),
        "differences": differences,
        "action_required": "manual_approval",
        "note": "Local YAML rules remain authoritative until accountant approval",
    }


def create_server() -> Server:
    server = Server("payroll-copilot-legal-sync")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="compare_vacation_rules",
                description="Compare local vacation.yaml against Kol Zchut vacation law",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "external_content": {
                            "type": "string",
                            "description": "Text content from Kol Zchut or government source",
                        }
                    },
                    "required": ["external_content"],
                },
            ),
            Tool(
                name="compare_overtime_rules",
                description="Compare local overtime.yaml against external overtime regulations",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "external_content": {"type": "string"},
                    },
                    "required": ["external_content"],
                },
            ),
            Tool(
                name="compare_minimum_wage",
                description="Compare local labor_law.yaml minimum wage against current official rate",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "external_content": {"type": "string"},
                        "official_rate": {"type": "number"},
                    },
                    "required": ["external_content"],
                },
            ),
            Tool(
                name="fetch_local_rule",
                description="Retrieve current local YAML rule file content",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "enum": [
                                "labor_law.yaml",
                                "overtime.yaml",
                                "vacation.yaml",
                                "tax.yaml",
                                "pension.yaml",
                                "transportation.yaml",
                            ],
                        }
                    },
                    "required": ["filename"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name == "compare_vacation_rules":
            local = load_yaml_rule("vacation.yaml")
            result = compare_rules(local, arguments.get("external_content", ""))
        elif name == "compare_overtime_rules":
            local = load_yaml_rule("overtime.yaml")
            result = compare_rules(local, arguments.get("external_content", ""))
        elif name == "compare_minimum_wage":
            local = load_yaml_rule("labor_law.yaml")
            external = arguments.get("external_content", "")
            official_rate = arguments.get("official_rate")
            local_rate = (
                local.get("rules", {})
                .get("minimum_wage_hourly", {})
                .get("parameters", {})
                .get("amount")
            )
            result = {
                "local_rate": local_rate,
                "official_rate": official_rate,
                "match": local_rate == official_rate,
                "action_required": "manual_approval" if local_rate != official_rate else "none",
            }
        elif name == "fetch_local_rule":
            filename = arguments.get("filename", "")
            content = load_yaml_rule(filename)
            result = {"filename": filename, "content": content}
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    return server


async def main() -> None:
    if Server is None:
        raise RuntimeError("MCP package not installed. Install with: pip install mcp")

    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
