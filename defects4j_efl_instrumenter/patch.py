from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _clean_diff_path(value: str) -> str:
    value = value.strip().strip('"').split("\t", 1)[0]
    if value == "/dev/null":
        return value
    if value.startswith("a/") or value.startswith("b/") or value.startswith("a\\") or value.startswith("b\\"):
        value = value[2:]
    return Path(value).as_posix()


def source_changes(buggy: Path, fixed: Path, *, source_prefix: str = "") -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["git", "diff", "--no-index", "--unified=0", "--", str(buggy), str(fixed)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(f"git diff failed: {completed.stderr[-4000:]}")

    changes: list[dict[str, Any]] = []
    old_file = ""
    new_file = ""
    for line in completed.stdout.splitlines():
        if line.startswith("--- "):
            old_file = _clean_diff_path(line[4:])
            continue
        if line.startswith("+++ "):
            new_file = _clean_diff_path(line[4:])
            continue
        match = _HUNK.match(line)
        if not match:
            continue
        old_start = int(match.group(1))
        old_count = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_count = int(match.group(4) or 1)
        if old_count and new_count:
            kind = "replacement"
        elif old_count:
            kind = "deletion"
        else:
            kind = "insertion"
        selected = old_file if old_file != "/dev/null" else new_file
        normalized = selected.replace("\\", "/")
        relative = None
        norm_path = Path(selected)
        for root in (buggy, fixed):
            try:
                # Attempt relative_to using resolved paths to handle symlinks and 8.3 names
                relative = norm_path.resolve().relative_to(root.resolve()).as_posix()
                break
            except Exception:
                pass
            marker = root.resolve().as_posix().lstrip("/") + "/"
            candidate = normalized.lstrip("/")
            position = candidate.find(marker)
            if position >= 0:
                relative = candidate[position + len(marker):]
                break
        if relative is None:
            relative = Path(normalized).name
        if not relative.endswith(".java"):
            continue
        selected = "/".join(part for part in (source_prefix.strip("/"), relative.strip("/")) if part)
        changes.append(
            {
                "file": selected,
                "faulty_lines": list(range(old_start, old_start + old_count)) if old_count else [],
                "fixed_lines": list(range(new_start, new_start + new_count)) if new_count else [],
                "change_type": kind,
                "header": False,
                "exact_buggy_location": bool(old_count),
            }
        )
    return changes
