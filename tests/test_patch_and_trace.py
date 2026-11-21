from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from defects4j_efl_instrumenter.patch import source_changes
from defects4j_efl_instrumenter.models import TestRun
from defects4j_efl_instrumenter.trace import (
    iter_trace_file,
    merge_trace_directory,
    resolve_fault_predicates,
    write_standard_matrix_dataset,
    write_tagged_matrix_dataset,
)


class PatchAndTraceTests(unittest.TestCase):
    def test_source_change_maps_buggy_java_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            buggy = root / "buggy" / "src"
            fixed = root / "fixed" / "src"
            (buggy / "p").mkdir(parents=True)
            (fixed / "p").mkdir(parents=True)
            (buggy / "p" / "A.java").write_text(
                "class A {\n  int f() {\n    return 0;\n  }\n}\n", encoding="utf-8"
            )
            (fixed / "p" / "A.java").write_text(
                "class A {\n  int f() {\n    return 1;\n  }\n}\n", encoding="utf-8"
            )
            changes = source_changes(buggy, fixed, source_prefix="src")
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["file"], "src/p/A.java")
            self.assertEqual(changes[0]["faulty_lines"], [3])
            self.assertEqual(changes[0]["change_type"], "replacement")

    def test_binary_trace_merge_and_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.mkdir()
            (raw / "trace-1.bin").write_bytes(b"".join(struct.pack(">i", value) for value in (1, 2)))
            (raw / "trace-2.bin").write_bytes(b"".join(struct.pack(">i", value) for value in (3, 4)))
            destination = root / "trace.bin"
            count = merge_trace_directory(raw, destination)
            self.assertEqual(count, 4)
            self.assertEqual(list(iter_trace_file(destination)), [1, 2, 3, 4])

    def test_standard_and_tagged_matrix_dataset_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            t1_file = root / "t1.bin"
            t2_file = root / "t2.bin"
            t3_file = root / "t3.bin"

            t1_file.write_bytes(b"".join(struct.pack(">i", v) for v in (1, 2, 3)))
            t2_file.write_bytes(b"".join(struct.pack(">i", v) for v in (1, 4, 5)))
            t3_file.write_bytes(b"".join(struct.pack(">i", v) for v in (2, 3, 4)))

            runs = [
                TestRun(test="test1", result="T", trace_file=t1_file, trace_count=3),
                TestRun(test="test2", result="T", trace_file=t2_file, trace_count=3),
                TestRun(test="test3", result="F", trace_file=t3_file, trace_count=3),
            ]

            dataset_txt = root / "v1_dataset.txt"
            write_standard_matrix_dataset(dataset_txt, runs)
            lines = dataset_txt.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4)
            self.assertEqual(lines[0], "P1,P2,P3")
            self.assertEqual(lines[1], "P1,P4,P5")
            self.assertEqual(lines[2], "P2,P3,P4")
            self.assertEqual(lines[3], "T,T,F")

            # With P4 as a fault predicate:
            # test1: T, no P4 -> PASS (T)
            # test2: T, has P4 -> CC (CC)
            # test3: F, has P4 -> FAIL (F)
            tagged_txt = root / "v1_tagged.txt"
            info = write_tagged_matrix_dataset(tagged_txt, runs, fault_predicates={4})
            tagged_lines = tagged_txt.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(tagged_lines), 4)
            self.assertEqual(tagged_lines[3], "T,CC,F")
            self.assertEqual(info["n_pass"], 1)
            self.assertEqual(info["n_cc"], 1)
            self.assertEqual(info["n_fail"], 1)


if __name__ == "__main__":
    unittest.main()
