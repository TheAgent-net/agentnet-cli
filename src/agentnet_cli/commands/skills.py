from __future__ import annotations

import json

import typer

skills_app = typer.Typer(help="Search, browse, and discover AI agent skills.")


def _die(message: str) -> None:
    print(json.dumps({"error": message}))
    raise SystemExit(1)


@skills_app.command()
def search(
    query: str = typer.Argument(help="Keyword to search for"),
    limit: int = typer.Option(20, "--limit", "-l", help="Results to return"),
    source: str = typer.Option(
        "skillssh", "--source", "-s",
        help="Source: skillssh (default) or skillsmp",
    ),
    page: int = typer.Option(1, "--page", "-p", help="Page number (skillsmp only)"),
    sort: str = typer.Option("recent", "--sort", help="Sort by: recent or stars (skillsmp only)"),
    category: str | None = typer.Option(None, "--category", "-c", help="Category filter (skillsmp only)"),
) -> None:
    """Search for AI agent skills. Uses skills.sh by default."""
    if source == "skillsmp":
        from ..skills.skillsmp import SkillsMPClient, SkillsMPError

        with SkillsMPClient() as client:
            try:
                result = client.search(
                    query=query, limit=limit, page=page, sort_by=sort, category=category,
                )
                print(json.dumps(result, indent=2))
            except SkillsMPError as e:
                _die(str(e))
    else:
        from ..skills.client import SkillsClient, SkillsError

        with SkillsClient() as client:
            try:
                result = client.search(query=query, limit=limit)
                print(json.dumps(result, indent=2))
            except SkillsError as e:
                _die(str(e))


@skills_app.command()
def discover(
    use_case: str = typer.Argument(help="Describe what you need (e.g. 'set up CI/CD for a React app')"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results to return"),
) -> None:
    """AI-powered skill discovery across all sources.

    Tries agentnet platform first (server-side AI). Falls back to local
    mode with OPENAI_API_KEY or ANTHROPIC_API_KEY. Works without any key
    using deterministic multi-source search.
    """
    import os

    from ..config import load_config
    from ..skills.discovery import SkillDiscovery

    config = load_config() or {}
    with SkillDiscovery(
        platform_url=config.get("platform_url"),
        api_token=config.get("api_token"),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
    ) as disco:
        try:
            result = disco.discover(use_case=use_case, limit=limit)
            print(json.dumps(result, indent=2))
        except Exception as e:
            _die(str(e))
