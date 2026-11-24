from __future__ import annotations
import gzip, tempfile, unittest
from pathlib import Path
from defects4j_efl_instrumenter.cache_support import write_cache_manifest
from defects4j_efl_instrumenter.models import BugRef
from defects4j_efl_instrumenter.runner import _result_cache_status, _dataset_name

class ResultCacheTests(unittest.TestCase):
    def test_validated_cache_rejects_tampering_and_config_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bug = BugRef('Lang', 1)
            with gzip.open(root / _dataset_name(bug), 'wt', encoding='utf-8') as stream:
                stream.write('test_id\tstatus\tcc\tpath\nT1\tF\t0\t1\n')
            files = {
                'complete.json': '{"complete":true}',
                'tests.tsv': 'test_id\ttest_name\tstatus\tcc\tincluded\ttrace_len\tduration_sec\treturn_code\ttimed_out\treason\nT1\tA#t\tF\t0\t1\t1\t0.1\t1\t0\t\n',
                'summary.json': '{"schema":"efl-dataset-v2"}',
                'source_map.csv': 'predicate,id,file,line\nP1,1,A.java,1\n',
                'source_changes.json': '[]',
                'metadata.json': '{"program":"Lang"}',
            }
            for name, text in files.items():
                (root / name).write_text(text, encoding='utf-8')
            outputs = [root / _dataset_name(bug)] + [root / name for name in files]
            write_cache_manifest(root, fp='fp1', options={}, outputs=outputs)
            self.assertEqual(_result_cache_status(root, bug, 'fp1'), (True, 'complete'))
            ok, reason = _result_cache_status(root, bug, 'fp2')
            self.assertFalse(ok)
            self.assertIn('fingerprint changed', reason)
            (root / 'tests.tsv').write_text('changed\n', encoding='utf-8')
            ok, reason = _result_cache_status(root, bug, 'fp1')
            self.assertFalse(ok)
            self.assertIn('checksum changed', reason)

if __name__ == '__main__':
    unittest.main()
