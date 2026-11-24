from __future__ import annotations

import gzip
import json
import struct
import tempfile
import unittest
from pathlib import Path

from defects4j_efl_instrumenter.patch import source_changes
from defects4j_efl_instrumenter.models import TestRun
from defects4j_efl_instrumenter.trace import (
    iter_trace_file,
    merge_trace_directory,
    write_tests_tsv,
    write_traces_tsv_gz,
    write_version_summary,
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

    def test_traces_tsv_gz_and_summary_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            t1_file = root / "t1.bin"
            t2_file = root / "t2.bin"
            t3_file = root / "t3.bin"

            t1_file.write_bytes(b"".join(struct.pack(">i", v) for v in (1, 2, 3)))
            t2_file.write_bytes(b"".join(struct.pack(">i", v) for v in (1, 4, 5)))
            t3_file.write_bytes(b"".join(struct.pack(">i", v) for v in (2, 3, 4)))

            runs = [
                TestRun(test="pkg.A#test1", result="T", trace_file=t1_file, trace_count=3),
                TestRun(test="pkg.A#test2", result="T", trace_file=t2_file, trace_count=3),
                TestRun(test="pkg.A#test3", result="F", trace_file=t3_file, trace_count=3),
            ]

            traces_gz = root / "traces.tsv.gz"
            info = write_traces_tsv_gz(traces_gz, runs, fault_predicates={4})
            with gzip.open(traces_gz, "rt", encoding="utf-8") as stream:
                lines = stream.read().splitlines()
            self.assertEqual(
                lines,
                [
                    "test_id\tstatus\tcc\tpath",
                    "T1\tT\t0\t1 2 3",
                    "T2\tT\t1\t1 4 5",
                    "T3\tF\t0\t2 3 4",
                ],
            )
            self.assertEqual(info["n_pass"], 1)
            self.assertEqual(info["n_cc"], 1)
            self.assertEqual(info["n_fail"], 1)

            tests_tsv = root / "tests.tsv"
            write_tests_tsv(tests_tsv, info["included_rows"])
            test_lines = tests_tsv.read_text(encoding="utf-8").splitlines()
            self.assertTrue(test_lines[0].startswith("test_id\ttest_name\tstatus\tcc\tincluded"))
            self.assertIn("T2\tpkg.A#test2\tT\t1\t1\t3", test_lines[2])

            summary_json = root / "summary.json"
            write_version_summary(
                summary_json,
                benchmark="Defects4J",
                project="Lang",
                bug_id=1,
                test_set="relevant",
                instrument_scope="relevant",
                fault_predicates={4},
                tag_info=info,
                tests_discovered=3,
                tests_excluded=0,
                total_events=9,
                max_events=3,
                min_events=3,
            )
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["schema"], "efl-dataset-v2")
            self.assertEqual(summary["fault_predicate_ids"], [4])
            self.assertEqual(summary["counts"], {"pass_clean": 1, "coincidental_correct": 1, "fail": 1})


if __name__ == "__main__":
    unittest.main()
