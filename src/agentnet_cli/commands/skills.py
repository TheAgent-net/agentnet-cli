from __future__ import annotations

import json

import typer

from ..skills.client import SkillsClient, SkillsError

skills_app = typer.Typer(help="Search and browse AI agent skills from SkillsMP.")


def _die(message: str) -> None:
    print(json.dumps({"error": message}))
    raise SystemExit(1)


@skills_app.command()
def search(
    query: str = typer.Argument(help="Keyword to search for"),
    limit: int = typer.Option(20, "--limit", "-l", help="Results per page (1-50)"),
    page: int = typer.Option(1, "--page", "-p", help="Page number"),
    sort: str = typer.Option("recent", "--sort", "-s", help="Sort by: recent or stars"),
    category: str | None = typer.Option(None, "--category", "-c", help="Category slug (e.g. data-ai)"),
) -> None:
    """Search for AI agent skills on SkillsMP."""
    with SkillsClient() as client:
        try:
            result = client.search(
                query=query,
                limit=limit,
                page=page,
                sort_by=sort,
                category=category,
            )
            print(json.dumps(result, indent=2))
        except SkillsError as e:
            _die(str(e))
