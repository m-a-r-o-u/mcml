from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .db import Person, connect, fetch_all, init_db, last_updated, replace_all_people, default_db_path
from .match import find_best_matches
from .scrape import scrape_all

app = typer.Typer(add_completion=False, help="Query MCML people from a local database.")
console = Console()


def _render_matches(matches: list, title: str = "Matches") -> None:
    table = Table(title=title)
    table.add_column("score", justify="right")
    table.add_column("name")
    table.add_column("role")
    table.add_column("note")
    table.add_column("mcml_url")
    for m in matches:
        table.add_row(f"{m.score:.2f}", m.full_name, m.role, m.note, m.mcml_url)
    console.print(table)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    first: Optional[str] = typer.Option(None, "--first", help="First name (can be partial/misspelled)."),
    last: Optional[str] = typer.Option(None, "--last", help="Last name (can be partial/misspelled)."),
    limit: int = typer.Option(10, "--limit", min=1, max=50, help="Maximum number of results."),
    db: Optional[Path] = typer.Option(None, "--db", help="Path to the SQLite DB (optional)."),
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
):
    """Run a fuzzy lookup when --first/--last are given, otherwise show help."""
    if version:
        console.print(__version__)
        raise typer.Exit(0)

    if ctx.invoked_subcommand is not None:
        return

    if not first and not last:
        console.print(ctx.get_help())
        raise typer.Exit(0)

    query = " ".join([p for p in [first, last] if p])

    con = connect(db)
    init_db(con)
    rows = [dict(r) for r in fetch_all(con)]
    if not rows:
        console.print(f"Database is empty. Run 'mcml export' first. DB: {default_db_path()}")
        raise typer.Exit(2)

    matches = find_best_matches(query, rows, first=first, last=last, limit=limit)
    if not matches:
        console.print("No close matches found.")
        raise typer.Exit(1)

    _render_matches(matches, title=f"MCML candidates for: {query}")


@app.command()
def export(
    db: Optional[Path] = typer.Option(None, "--db", help="Path to the SQLite DB (optional)."),
):
    """Scrape mcml.ai/team subpages and rebuild the local SQLite database."""
    con = connect(db)
    init_db(con)
    people = scrape_all()
    n = replace_all_people(con, people)
    console.print(f"Stored {n} people in {db or default_db_path()}")


@app.command()
def check(
    first: Optional[str] = typer.Option(None, "--first", help="First name (exact or partial)."),
    last: Optional[str] = typer.Option(None, "--last", help="Last name (exact or partial)."),
    db: Optional[Path] = typer.Option(None, "--db", help="Path to the SQLite DB (optional)."),
):
    """Return a simple yes/no and show top matches."""
    if not first and not last:
        console.print("Please provide --first and/or --last.")
        raise typer.Exit(2)

    query = " ".join([p for p in [first, last] if p])
    con = connect(db)
    init_db(con)
    rows = [dict(r) for r in fetch_all(con)]
    if not rows:
        console.print("Database is empty. Run 'mcml export' first.")
        raise typer.Exit(2)

    matches = find_best_matches(query, rows, first=first, last=last, limit=5, threshold=0.55)
    if matches and matches[0].score >= 0.85:
        console.print("Yes, likely an MCML member.")
    else:
        console.print("No strong match found in the local DB.")
    if matches:
        _render_matches(matches, title=f"Top matches for: {query}")


@app.command()
def info(
    db: Optional[Path] = typer.Option(None, "--db", help="Path to the SQLite DB (optional)."),
):
    """Show database location and last update timestamp."""
    con = connect(db)
    init_db(con)
    ts = last_updated(con)
    console.print(f"DB: {db or default_db_path()}")
    console.print(f"Last updated (UTC): {ts or 'never'}")
