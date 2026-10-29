"""Package the new attempt, including incomplete results, without modifying old data."""
import argparse
import json
import zipfile
from pathlib import Path
from common import sha,save

def main(root):
    root=root.resolve();assert root.name=='experiment_bundle' and (root/'package_origin.json').is_file()
    paths=sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.name!='SHA256SUMS')
    (root/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(root).as_posix()}\n' for p in paths),encoding='utf-8')
    dest=root.parent/'coco400_results.zip';assert not dest.exists(),'Refuse to overwrite existing result archive'
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths+[root/'SHA256SUMS']:z.write(p,'experiment_bundle/'+p.relative_to(root).as_posix())
    with zipfile.ZipFile(dest) as z:assert z.testzip() is None
    checksum=sha(dest);dest.with_suffix('.zip.sha256').write_text(f'{checksum}  {dest.name}\n')
    print(json.dumps(dict(archive=str(dest),bytes=dest.stat().st_size,sha256=checksum,files=len(paths)+1)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);a=p.parse_args();main(a.bundle)
