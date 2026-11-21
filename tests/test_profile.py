from __future__ import annotations

import unittest
from pathlib import Path

from defects4j_efl_instrumenter.runner import resolve_bugs


class PaperProfileTests(unittest.TestCase):
    def test_scd4fl_profile_has_expected_defects4j_versions(self) -> None:
        bugs = resolve_bugs(
            Path("/not-used-for-profile"),
            projects=None,
            bug_ids=None,
            include_deprecated=True,
            profile="scd4fl-2024",
        )
        self.assertEqual(len(bugs), 395)
        counts: dict[str, int] = {}
        for bug in bugs:
            counts[bug.project] = counts.get(bug.project, 0) + 1
        self.assertEqual(
            counts,
            {
                "Chart": 26,
                "Math": 106,
                "Lang": 65,
                "Time": 27,
                "Mockito": 38,
                "Closure": 133,
            },
        )


if __name__ == "__main__":
    unittest.main()
