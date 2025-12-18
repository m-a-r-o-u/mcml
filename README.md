# mcml-cli

A small Python CLI that:

1. Scrapes MCML people from https://mcml.ai/team/ (and its subpages).
2. Stores the results in a local SQLite database.
3. Lets you query the database by name (supports typos and partial names).

## Install (editable)

```bash
cd mcml-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Update the local database

```bash
mcml export
```

This command re-scrapes the MCML pages and rebuilds the SQLite database (default location: `~/.local/share/mcml/mcml.sqlite`).

## Search for a person

```bash
mcml --first Daniel --last Cremers
mcml --first Dan --last Cremer
mcml --last Bischl
```

## Check membership (yes/no plus top matches)

```bash
mcml check --first Daniel --last Cremers
```

## Database info

```bash
mcml info
```

## Notes

- The scraper uses best-effort HTML heuristics that work with the current MCML page layout. If the layout changes, you may need to tweak `src/mcml_cli/scrape.py`.
- For many people, MCML does not provide a dedicated personal profile page. In those cases, the tool stores the most relevant MCML link it can find, typically the associated research group page.
