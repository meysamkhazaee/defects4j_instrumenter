from __future__ import annotations

import csv
import hashlib
import json
import struct
from pathlib import Path
from typing import Iterable, Iterator

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


def write_efl_input(path: Path, runs: Iterable[TestRun]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(1024 * 1024 * 1024)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        for run in runs:
            if run.result not in {"T", "F"} or not run.trace_file or run.trace_count <= 0:
                continue
            writer.writerow([run.test, run.result, ",".join(f"P{value}" for value in iter_trace_file(run.trace_file))])


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


def write_standard_matrix_dataset(path: Path, runs: list[TestRun]) -> None:
    """Write standard FL/ML dataset: lines 1..N are P-traces, line N+1 is the T/F verdict vector."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="\n", encoding="utf-8") as stream:
        for run in runs:
            trace_str = ",".join(f"P{val}" for val in iter_trace_file(run.trace_file))
            stream.write(trace_str + "\n")
        verdicts = ",".join(run.result for run in runs)
        stream.write(verdicts + "\n")


def write_tagged_matrix_dataset(
    path: Path,
    runs: list[TestRun],
    fault_predicates: set[int],
) -> dict[str, Any]:
    """Write tagged dataset with Coincidental Correctness (CC) identification."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tags_rich = []
    classifications = []
    tests_detail = []
    n_pass = 0
    n_cc = 0
    n_fail = 0

    with path.open("w", newline="\n", encoding="utf-8") as stream:
        for run in runs:
            trace_vals = list(iter_trace_file(run.trace_file))
            trace_str = ",".join(f"P{val}" for val in trace_vals)
            stream.write(trace_str + "\n")

            fault_visited = bool(fault_predicates and any(p in fault_predicates for p in trace_vals))

            if run.result == "F":
                tag_strict = "F"
                tag_rich = "F"
                classification = "FAIL"
                n_fail += 1
            elif fault_visited:
                tag_strict = "T"
                tag_rich = "CC"
                classification = "COINCIDENTAL_CORRECT"
                n_cc += 1
            else:
                tag_strict = "T"
                tag_rich = "T"
                classification = "PASS"
                n_pass += 1

            tags_rich.append(tag_rich)
            classifications.append(classification)
            tests_detail.append({
                "test": run.test,
                "result": run.result,
                "classification": classification,
                "tag_strict": tag_strict,
                "tag_rich": tag_rich,
                "fault_visited": fault_visited,
                "trace_len": len(trace_vals),
            })

        verdicts_cc = ",".join(tags_rich)
        stream.write(verdicts_cc + "\n")

    return {
        "n_pass": n_pass,
        "n_cc": n_cc,
        "n_fail": n_fail,
        "tags_rich": tags_rich,
        "tests_detail": tests_detail,
    }


def write_detailed_summary(
    path: Path,
    project: str,
    bug_id: int,
    runs: list[TestRun],
    fault_predicates: set[int],
    tag_info: dict[str, Any],
    duration: float = 0.0,
) -> None:
    """Write comprehensive JSON metadata matching the Siemens detailed format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    detailed = {
        "benchmark": "Defects4J",
        "project": project,
        "version": f"v{bug_id}",
        "total_tests": len(runs),
        "duration_sec": round(duration, 2),
        "fault_predicates": [f"P{p}" for p in sorted(fault_predicates)],
        "summary": {
            "pass": tag_info.get("n_pass", 0),
            "coincidental_correct": tag_info.get("n_cc", 0),
            "fail": tag_info.get("n_fail", 0),
        },
        "verdict_vector_strict": [r.result for r in runs],
        "verdict_vector_tagged": tag_info.get("tags_rich", []),
        "tests": tag_info.get("tests_detail", []),
    }
    write_json(path, detailed)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
