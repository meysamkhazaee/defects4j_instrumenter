from __future__ import annotations

import unittest
from unittest import mock

from defects4j_efl_instrumenter.runner import resolve_instrument_jobs


class ParallelismTests(unittest.TestCase):
    def test_explicit_jobs_are_preserved(self) -> None:
        jobs, detail = resolve_instrument_jobs(4)
        self.assertEqual(jobs, 4)
        self.assertIn("explicit=4", detail)

    def test_auto_jobs_are_cpu_and_memory_bounded(self) -> None:
        with mock.patch("defects4j_efl_instrumenter.runner.os.cpu_count", return_value=16), \
             mock.patch("defects4j_efl_instrumenter.runner._available_memory_bytes", return_value=16 * 1024**3):
            jobs, detail = resolve_instrument_jobs(0)
        self.assertEqual(jobs, 5)
        self.assertIn("auto", detail)

    def test_negative_jobs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_instrument_jobs(-1)


if __name__ == "__main__":
    unittest.main()
