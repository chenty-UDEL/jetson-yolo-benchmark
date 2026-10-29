"""Offline verification; standard library only."""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def verify(root=ROOT):
    entries=(root/'SHA256SUMS').read_text('utf-8').splitlines()
    for line in entries:
        digest,rel=line.split('  ',1)
        path=(root/rel).resolve()
        assert path.is_relative_to(root.resolve()), rel
        assert path.is_file() and sha(path)==digest,rel
    manifest=json.loads((root/'dataset/dataset_manifest.json').read_text('utf-8'))
    rows=manifest['frames']; assert len(rows)==400
    assert Counter(r['group'] for r in rows)=={'positive':200,'negative':200}
    assert len({r['coco_image_id'] for r in rows})==400
    assert len({r['file_sha256'] for r in rows})==400
    gt=json.loads((root/'dataset/annotations/instances_coco400.json').read_text('utf-8'))
    ids={a['image_id'] for a in gt['annotations']}
    assert {x['id'] for x in gt['images']}=={r['coco_image_id'] for r in rows}
    assert len(list((root/'dataset/images').rglob('*.jpg')))==400
    for r in rows:
        assert sha(root/r['path'])==r['file_sha256'],r['path']
        assert (r['coco_image_id'] in ids)==(r['group']=='positive'),r['frame_id']
    result=dict(passed=True,verified_files=len(entries),**manifest['statistics'])
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

if __name__=='__main__':verify()
