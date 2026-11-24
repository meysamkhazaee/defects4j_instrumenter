from __future__ import annotations

import csv
import gzip
import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Iterable, Iterator

from .models import TestRun


def safe_test_id(test: str) -> str:
    digest = hashlib.sha1(test.encode("utf-8")).hexdigest()[:12]
    prefix = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in test)[:80]
    return f"{prefix}-{digest}"


def iter_trace_file(path: Path, *, chunk_bytes: int = 4 * 16384) -> Iterator[int]:
    with path.open("rb") as stream:
        remainder = b""
        while True:
            chunk = stream.read(chunk_bytes)
            if not chunk:
                break
            data = remainder + chunk
            aligned = len(data) - (len(data) % 4)
            for value in struct.iter_unpack(">i", data[:aligned]):
                yield value[0]
            remainder = data[aligned:]
        if remainder:
            raise ValueError(f"Corrupt binary trace (size is not divisible by 4): {path}")


def merge_trace_directory(path: Path, destination: Path) -> int:
    files = sorted(path.glob("trace-*.bin"), key=lambda item: (item.stat().st_mtime_ns, item.name))
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("wb") as output:
        for file in files:
            size = file.stat().st_size
            if size % 4:
                raise ValueError(f"Corrupt binary trace (size is not divisible by 4): {file}")
            count += size // 4
            with file.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
    return count


def resolve_fault_predicates(source_map_path: Path, source_changes_path: Path) -> set[int]:
    """Identify which predicate IDs correspond to mutated lines in buggy source code."""
    if not source_map_path.is_file() or not source_changes_path.is_file():
        return set()
    try:
        changes = json.loads(source_changes_path.read_text(encoding="utf-8"))
    except Exception:
        return set()

    faulty_file_lines: dict[str, set[int]] = {}
    for ch in changes:
        f = ch.get("file", "").replace("\\", "/").strip("/")
        lines = set(ch.get("faulty_lines", []))
        if f and lines:
            faulty_file_lines[f] = faulty_file_lines.get(f, set()) | lines

    if not faulty_file_lines:
        return set()

    fault_preds: set[int] = set()
    try:
        with source_map_path.open("r", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            for row in reader:
                pred_id = int(row["id"])
                file_path = row["file"].replace("\\", "/").strip("/")
                line_no = int(row["line"])
                for f, lines in faulty_file_lines.items():
                    if (file_path == f or file_path.endswith("/" + f) or f.endswith("/" + file_path)) and line_no in lines:
                        fault_preds.add(pred_id)
                        break
    except Exception:
        pass
    return fault_preds


def write_traces_tsv_gz(
    path: Path,
    runs: Iterable[TestRun],
    fault_predicates: set[int],
    *,
    compresslevel: int = 6,
) -> dict[str, Any]:
    """Write the canonical gzip-compressed TSV trace file (`traces.tsv.gz`).

    Columns: ``test_id``, ``status`` (``T``/``F``), ``cc`` (``1``/``0``), ``path``
    (space-separated integer predicate IDs matching ``source_map.csv`` ``id``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n_pass = 0
    n_cc = 0
    n_fail = 0
    included_rows: list[dict[str, Any]] = []

    with gzip.open(path, "wt", encoding="utf-8", newline="\n", compresslevel=compresslevel) as stream:
        stream.write("test_id\tstatus\tcc\tpath\n")
        for idx, run in enumerate(runs, start=1):
            if run.result not in {"T", "F"} or not run.trace_file or run.trace_count <= 0:
                continue
            test_id = f"T{idx}"
            fault_visited = False
            tokens: list[str] = []
            for pred_id in iter_trace_file(run.trace_file):
                if fault_predicates and not fault_visited and pred_id in fault_predicates:
                    fault_visited = True
                tokens.append(str(pred_id))
            if not tokens:
                continue

            if run.result == "F":
                cc_flag = 0
                n_fail += 1
            elif fault_visited:
                cc_flag = 1
                n_cc += 1
            else:
                cc_flag = 0
                n_pass += 1

            stream.write(f"{test_id}\t{run.result}\t{cc_flag}\t{' '.join(tokens)}\n")
            included_rows.append(
                {
                    "test_id": test_id,
                    "test_name": run.test,
                    "status": run.result,
                    "cc": cc_flag,
                    "included": 1,
                    "trace_len": len(tokens),
                    "duration_sec": round(run.duration_seconds, 4),
                    "return_code": run.return_code,
                    "timed_out": int(run.timed_out),
                    "reason": "",
                }
            )

    return {
        "n_pass": n_pass,
        "n_cc": n_cc,
        "n_fail": n_fail,
        "included_rows": included_rows,
    }


def write_tests_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write human-readable per-test metadata and test_id -> test_name mapping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "test_id\ttest_name\tstatus\tcc\tincluded\ttrace_len\tduration_sec\treturn_code\ttimed_out\treason\n"
        )
        for row in rows:
            safe_name = str(row["test_name"]).replace("\t", " ").replace("\r", " ").replace("\n", " ")
            safe_reason = str(row.get("reason", "")).replace("\t", " ").replace("\r", " ").replace("\n", " ")
            stream.write(
                f"{row['test_id']}\t{safe_name}\t{row['status']}\t{row['cc']}\t"
                f"{row['included']}\t{row['trace_len']}\t{row['duration_sec']}\t"
                f"{row['return_code']}\t{row['timed_out']}\t{safe_reason}\n"
            )


def write_version_summary(
    path: Path,
    *,
    benchmark: str,
    project: str,
    bug_id: int,
    test_set: str,
    instrument_scope: str,
    fault_predicates: set[int],
    tag_info: dict[str, Any],
    tests_discovered: int,
    tests_excluded: int,
    total_events: int,
    max_events: int,
    min_events: int,
    duration: float = 0.0,
) -> None:
    """Write compact version summary JSON without duplicating trace sequences."""
    included_rows = tag_info.get("included_rows", [])
    summary = {
        "schema": "efl-dataset-v2",
        "benchmark": benchmark,
        "project": project,
        "version": f"v{bug_id}",
        "test_set": test_set,
        "instrumentation": {
            "granularity": "bytecode_line",
            "engine": "java_asm_agent",
            "scope": instrument_scope,
            "predicate_format": "integer_id_matching_source_map_id",
        },
        "files": {
            "traces": "traces.tsv.gz",
            "tests": "tests.tsv",
            "source_map": "source_map.csv",
            "source_changes": "source_changes.json",
            "metadata": "metadata.json",
        },
        "duration_sec": round(duration, 2),
        "tests_discovered": tests_discovered,
        "tests_included": len(included_rows),
        "tests_excluded": tests_excluded,
        "total_trace_events": total_events,
        "max_trace_events": max_events,
        "min_trace_events": min_events,
        "fault_predicates": [f"P{p}" for p in sorted(fault_predicates)],
        "fault_predicate_ids": sorted(fault_predicates),
        "counts": {
            "pass_clean": tag_info.get("n_pass", 0),
            "coincidental_correct": tag_info.get("n_cc", 0),
            "fail": tag_info.get("n_fail", 0),
        },
    }
    write_json(path, summary)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


DATASET_README_TEXT = """# EFL Dataset Format Guide (`efl-dataset-v2`)

Each `<program>/v<id>/<test_set>/` directory contains one compact, lossless dataset:

- `traces.tsv.gz`: Gzip-compressed UTF-8 TSV with header `test_id\\tstatus\\tcc\\tpath`.
  - `test_id`: Short test identifier (`T1`, `T2`, ...) mapped to the full test name in `tests.tsv`.
  - `status`: Strict oracle verdict (`T` = Pass, `F` = Fail).
  - `cc`: Ground-truth Coincidental Correctness flag (`1` if `status=T` and execution visited a fault predicate, else `0`).
  - `path`: Space-separated integer predicate IDs (`1 2 3 ...`) in exact execution order, matching `id` in `source_map.csv`.
- `tests.tsv`: Complete inventory of executed and excluded tests (`T1..TN` and `X1..XM`), mapping `test_id` to exact JUnit test method (`pkg.Class#method`) or Siemens `universe` command line, plus `status`, `cc`, `included`, `trace_len`, `duration_sec`, `return_code`, `timed_out`, `reason`.
- `source_map.csv`: Maps each integer predicate `id` (`P<id>`) to `file`, `line`, `column`, `function` (and bytecode `class,method,descriptor,event_type` for Defects4J or AST `kind` for Siemens).
- `source_changes.json`: Line-level diff between the healthy/fixed source and the buggy source (`file`, `kind`/`change_type`, `reference_lines`, `faulty_lines`, `reference_text`, `faulty_text`).
- `summary.json`: Compact version statistics, instrumentation metadata (`granularity`, `engine`, `scope`), and `fault_predicate_ids`.
- `metadata.json`: Benchmark, program, version, test set, and source/classpath metadata.
- `cache_manifest.json`: File sizes and SHA-256 checksums for EFL cache validation.

## Inspecting Traces

```bash
gzip -dc traces.tsv.gz | head -n 5
```

```python
import pandas as pd
traces = pd.read_csv("traces.tsv.gz", sep="\\t")
tests = pd.read_csv("tests.tsv", sep="\\t")
smap = pd.read_csv("source_map.csv")
```
"""


def write_dataset_readme(results_root: Path) -> None:
    results_root.mkdir(parents=True, exist_ok=True)
    readme = results_root / "DATASET_README.md"
    readme.write_text(DATASET_README_TEXT, encoding="utf-8")
