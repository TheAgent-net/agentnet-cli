from __future__ import annotations

import json

import typer

plugins_app = typer.Typer(help="Search plugin marketplaces for Claude Code and OpenClaw.")


def _die(message: str) -> None:
    print(json.dumps({"error": message}))
    raise SystemExit(1)


@plugins_app.command(name="search-claude")
def search_claude(
    query: str = typer.Argument(help="Keyword to search for"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results (1-50)"),
    category: str | None = typer.Option(
        None, "--category", "-c",
        help="Category filter (development, security, database, productivity, deployment, monitoring, design)",
    ),
) -> None:
    """Search the Claude Code plugin marketplace."""
    from ..plugins.claude_marketplace import ClaudeMarketplaceClient, ClaudeMarketplaceError

    with ClaudeMarketplaceClient() as client:
        try:
            result = client.search(query=query, limit=limit, category=category)
            print(json.dumps(result, indent=2))
        except ClaudeMarketplaceError as e:
            _die(str(e))


@plugins_app.command(name="search-clawhub")
def search_clawhub(
    query: str = typer.Argument(help="Keyword to search for"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results (1-100)"),
    category: str | None = typer.Option(
        None, "--category", "-c",
        help="Category filter (mcp-tooling, data, security, observability, automation, deployment, dev-tools)",
    ),
    family: str | None = typer.Option(
        None, "--family", "-f",
        help="Package type: skill, code-plugin, or bundle-plugin",
    ),
) -> None:
    """Search ClawHub (OpenClaw plugin marketplace)."""
    from ..plugins.clawhub import ClawHubClient, ClawHubError

    with ClawHubClient() as client:
        try:
            result = client.search(query=query, limit=limit, category=category, family=family)
            print(json.dumps(result, indent=2))
        except ClawHubError as e:
            _die(str(e))
