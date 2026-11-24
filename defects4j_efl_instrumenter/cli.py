from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .commands import configure_java_home, resolve_defects4j
from .progress import ConsoleReporter, LogLevel
from .runner import inspect_results, instrument_suite, resolve_bugs


def _csv_strings(value: str | None) -> set[str] | None:
    if not value:
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def _csv_ints(value: str | None) -> set[int] | None:
    if not value:
        return None
    return {int(item.strip()) for item in value.split(",") if item.strip()}


def _reporter(args: argparse.Namespace) -> ConsoleReporter:
    if args.progress_width < 10:
        raise ValueError("--progress-width must be at least 10")
    return ConsoleReporter(
        level=LogLevel.parse(args.log_level),
        progress_enabled=not args.no_progress,
        width=args.progress_width,
        stream=sys.stderr,
        error_stream=sys.stderr,
    )


def _add_ui(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--progress-width", type=int, default=32)


def _add_framework(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--defects4j",
        type=Path,
        help=(
            "Defects4J 3.0.1 source .zip, initialized root, or framework/bin/defects4j. "
            "A .zip is extracted and initialized once in --defects4j-cache."
        ),
    )
    parser.add_argument(
        "--defects4j-cache",
        type=Path,
        help="Extraction/setup cache for a Defects4J .zip; default: <work>/framework-cache",
    )
    parser.add_argument(
        "--defects4j-setup",
        choices=("auto", "never", "refresh"),
        default="auto",
        help="Reuse, prohibit, or refresh Defects4J initialization downloads",
    )
    parser.add_argument(
        "--java-home",
        type=Path,
        help="JDK 11 home used internally for Defects4J 3.0.1 and the Java agent",
    )


def _add_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--projects", help="Comma-separated Defects4J project IDs; default: all")
    parser.add_argument("--bugs", help="Comma-separated bug IDs applied to selected projects")
    parser.add_argument(
        "--profile",
        choices=("scd4fl-2024",),
        help="Use the six-project, 395-version Defects4J selection reported by SCD4FL",
    )
    parser.add_argument("--include-deprecated", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="defects4j-efl-data",
        description="Generate ordered EFL trace datasets from Defects4J buggy versions",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="List completed Defects4J EFL datasets")
    inspect.add_argument("--work", required=True, type=Path)
    _add_ui(inspect)

    prepare = sub.add_parser("prepare", help="Extract and initialize a Defects4J source archive")
    _add_framework(prepare)
    prepare.add_argument("--work", required=True, type=Path, help="Framework extraction/setup work directory")
    _add_ui(prepare)

    listing = sub.add_parser("list", help="List the project/bug selection without checking out code")
    _add_framework(listing)
    listing.add_argument("--work", type=Path, default=Path("work/defects4j-list"), help="Cache root when --defects4j is a .zip")
    _add_selection(listing)
    _add_ui(listing)

    instrument = sub.add_parser("instrument", help="Checkout, compile, instrument, and execute selected bugs")
    _add_framework(instrument)
    instrument.add_argument("--work", required=True, type=Path)
    _add_selection(instrument)
    instrument.add_argument("--test-selection", choices=("all", "relevant", "trigger"), default="all")
    instrument.add_argument("--tests", type=int, help="Limit test methods after trigger-first ordering")
    instrument.add_argument("--instrument-scope", choices=("relevant", "modified", "all"), default="relevant")
    instrument.add_argument("--test-timeout", type=float, default=300.0)
    instrument.add_argument("--validate-fixed", action="store_true", help="Run every selected test on the fixed version too")
    instrument.add_argument("--jobs", type=int, default=1, help="Bug versions processed concurrently; 0 = conservative auto sizing from CPU/RAM")
    instrument.add_argument("--cache", choices=("reuse", "refresh"), default="reuse")
    instrument.add_argument("--refresh-checkouts", action="store_true")
    instrument.add_argument("--keep-checkouts", action="store_true", default=False)
    instrument.add_argument("--remove-checkouts", action="store_false", dest="keep_checkouts")
    instrument.add_argument("--keep-raw-traces", action="store_true", default=False, help="Retain raw per-test binary trace.bin files after building traces.tsv.gz")
    instrument.add_argument("--asm-jar", type=Path, help="External ASM jar; required for Defects4J 2.x/Java 8")
    instrument.add_argument("--rebuild-agent", action="store_true")
    _add_ui(instrument)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        reporter = _reporter(args)
        if args.command == "inspect":
            payload = inspect_results(args.work)
            reporter.log(LogLevel.INFO, f"Discovered {len(payload)} Defects4J dataset(s)")
            print(json.dumps(payload, indent=2))
            return 0

        if os.name == "nt":
            raise RuntimeError(
                "Defects4J prepare/list/instrument requires POSIX shell/Perl tooling. "
                "Run this stage inside WSL2 on Windows; native Windows can inspect existing data and run EFL analysis/evaluation."
            )
        configure_java_home(args.java_home)
        cache_root = args.defects4j_cache or (args.work / "framework-cache")
        executable = resolve_defects4j(
            args.defects4j,
            cache_root=cache_root,
            setup_mode=args.defects4j_setup,
            reporter=reporter,
        )
        if args.command == "prepare":
            print(json.dumps({
                "root": str(executable.parents[2]),
                "executable": str(executable),
                "cache": str(cache_root.expanduser().resolve()),
            }, indent=2))
            return 0
        projects = _csv_strings(args.projects)
        bugs = _csv_ints(args.bugs)
        refs = resolve_bugs(
            executable,
            projects=projects,
            bug_ids=bugs,
            include_deprecated=args.include_deprecated or args.profile == "scd4fl-2024",
            profile=args.profile,
        )
        if args.command == "list":
            print(json.dumps([{"project": item.project, "bug_id": item.bug_id} for item in refs], indent=2))
            return 0

        instrument_suite(
            executable,
            args.work,
            refs,
            asm_jar=args.asm_jar,
            rebuild_agent=args.rebuild_agent,
            test_selection=args.test_selection,
            test_limit=args.tests,
            instrument_scope=args.instrument_scope,
            test_timeout=args.test_timeout,
            validate_fixed=args.validate_fixed,
            cache_mode=args.cache,
            refresh_checkouts=args.refresh_checkouts,
            keep_checkouts=args.keep_checkouts,
            keep_raw_traces=args.keep_raw_traces,
            jobs=args.jobs,
            reporter=reporter,
        )
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
