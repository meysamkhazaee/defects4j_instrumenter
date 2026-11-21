from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from defects4j_efl_instrumenter.cache_support import write_cache_manifest
from defects4j_efl_instrumenter.models import BugRef
from defects4j_efl_instrumenter.runner import _result_cache_status, _dataset_name

class ResultCacheTests(unittest.TestCase):
    def test_validated_cache_rejects_tampering_and_config_change(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); bug=BugRef('Lang',1)
            files={
                'complete.json':'{"complete":true}', _dataset_name(bug):'T1,F,"P1"\n',
                'source_map.csv':'predicate,id,file,line\nP1,1,A.java,1\n',
                'source_changes.json':'[]', 'metadata.json':'{"program":"Lang"}', 'tests.jsonl':'{"test":"T1"}\n'
            }
            for name,text in files.items(): (root/name).write_text(text)
            outputs=[root/name for name in files]
            write_cache_manifest(root, fp='fp1', options={}, outputs=outputs)
            self.assertEqual(_result_cache_status(root,bug,'fp1'),(True,'complete'))
            ok,reason=_result_cache_status(root,bug,'fp2'); self.assertFalse(ok); self.assertIn('fingerprint changed',reason)
            (root/'tests.jsonl').write_text('changed\n')
            ok,reason=_result_cache_status(root,bug,'fp1'); self.assertFalse(ok); self.assertIn('checksum changed',reason)

if __name__=='__main__': unittest.main()
