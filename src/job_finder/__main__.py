"""Command-line interface for job-finder."""

from __future__ import annotations

import argparse
import logging
import sys

from job_finder.config import ConfigError, load_config
from job_finder.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="job_finder",
        description="A free, scheduled job-search and CV-matching system.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to the YAML configuration file "
        "(overrides JOB_FINDER_CONFIG env var; default: config/config.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline without modifying the database or sending email.",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Do not send an email even if email is enabled in config.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override the maximum number of results to display.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG-level) logging.",
    )
    return parser


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the job-finder CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.error("Configuration error: %s", exc)
        return 1

    try:
        run_pipeline(
            config,
            dry_run=args.dry_run,
            no_email=args.no_email,
            limit=args.limit,
        )
    except Exception:
        logging.exception("Pipeline failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
