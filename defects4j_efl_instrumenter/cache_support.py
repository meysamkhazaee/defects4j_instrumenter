from __future__ import annotations
import hashlib, json
from pathlib import Path


def hash_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024), b''): h.update(c)
    return h.hexdigest()


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def write_cache_manifest(root: Path, *, fp: str, outputs: list[Path], options: dict) -> None:
    payload={'schema':1,'fingerprint':fp,'options':options,'outputs':[]}
    for p in outputs:
        payload['outputs'].append({'name':p.name,'size':p.stat().st_size,'sha256':hash_file(p)})
    (root/'cache_manifest.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')


def validate_cache_manifest(root: Path, fp: str) -> tuple[bool,str]:
    path=root/'cache_manifest.json'
    if not path.is_file(): return False,'cache_manifest.json missing'
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except Exception: return False,'cache_manifest.json invalid'
    if data.get('schema')!=1 or data.get('fingerprint')!=fp: return False,'cache fingerprint changed'
    for item in data.get('outputs',[]):
        p=root/item['name']
        if not p.is_file(): return False,f"missing {item['name']}"
        if p.stat().st_size!=item.get('size') or hash_file(p)!=item.get('sha256'): return False,f"checksum changed {item['name']}"
    return True,'validated'
