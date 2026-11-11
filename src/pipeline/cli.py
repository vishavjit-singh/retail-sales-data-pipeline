"""Command-line entry point: `python -m pipeline <command>`."""
from __future__ import annotations

import logging
import sqlite3
import sys

import click

from .config import load_config
from .generate import generate as generate_data
from .report import render_all
from .run import run_pipeline


@click.group()
@click.option("--config", "config_path", default=None, help="Path to pipeline.yaml")
@click.option("-v", "--verbose", is_flag=True)
@click.pass_context
def cli(ctx: click.Context, config_path: str | None, verbose: bool) -> None:
    """Retail sales ETL pipeline."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s")
    ctx.obj = load_config(config_path)


@cli.command()
@click.option("--days", default=90, show_default=True, help="Number of daily order files to have on disk.")
@click.pass_obj
def generate(cfg, days: int) -> None:
    """Create synthetic source data (idempotent: existing days are kept)."""
    click.echo(generate_data(cfg, days))


@cli.command()
@click.pass_obj
def run(cfg) -> None:
    """Load all order files not yet processed."""
    summary = run_pipeline(cfg)
    click.echo(summary)
    if summary.status == "failed":
        sys.exit(1)


@cli.command()
@click.pass_obj
def report(cfg) -> None:
    """Render charts from the warehouse into docs/images."""
    for p in render_all(cfg.warehouse, cfg.images_dir):
        click.echo(f"wrote {p}")


@cli.command()
@click.argument("sql")
@click.pass_obj
def query(cfg, sql: str) -> None:
    """Run an ad-hoc SQL query against the warehouse."""
    con = sqlite3.connect(cfg.warehouse)
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    click.echo("  ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        click.echo("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
