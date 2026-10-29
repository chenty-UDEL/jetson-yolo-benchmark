"""Create a new attempt and record old experiment hashes without writing to it."""
import argparse
import datetime as dt
import json
import shutil
from pathlib import Path
from verify_package import verify,sha,ROOT

def snapshot(root):
    return {str(p.relative_to(root)).replace('\\','/'):sha(p) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}

def setup(previous,output):
    previous=previous.resolve();output=output.resolve()
    assert previous.is_dir() and (previous/'config.json').is_file(),'Provide the existing controlled A experiment_bundle directory'
    assert output.name=='experiment_bundle','Output must end in experiment_bundle'
    assert not output.exists(),'Refusing to overwrite an existing attempt'
    assert not output.is_relative_to(previous) and not previous.is_relative_to(output),'Old and new experiments must be separate'
    verify()
    before=snapshot(previous)
    output.mkdir(parents=True,exist_ok=False)
    for folder in ('src','models','logs','controls','samples'):(output/folder).mkdir()
    shutil.copytree(ROOT/'dataset',output/'dataset')
    for p in (ROOT/'src').glob('*.py'):shutil.copyfile(p,output/'src'/p.name)
    for p in (ROOT/'reference/models').iterdir():shutil.copyfile(p,output/'models'/p.name)
    for name in ('model_manifest.json','engine_build.json'):shutil.copyfile(ROOT/'reference'/name,output/name)
    shutil.copyfile(ROOT/'reference/environment.json',output/'reference_environment.json')
    cfg=json.loads((ROOT/'reference/config.json').read_text('utf-8'))
    cfg.update(experiment_id='cisc662_v4_coco400_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),dataset_id='coco2017_val_reviewed400_v1',frames=400,manifest_sha256=None,control_plan_sha256=None,control_conditions_valid=False,control_limitations=['Pending live evidence-based validation'])
    (output/'config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    (output/'old_experiment_before.json').write_text(json.dumps(dict(root=str(previous),sha256=before),indent=2)+'\n')
    (output/'package_origin.json').write_text(json.dumps(dict(package_sha256sums_sha256=sha(ROOT/'SHA256SUMS'),package_root=str(ROOT),expected_formal_rows=4000,expected_warmups=500),indent=2)+'\n')
    print('NEW EXPERIMENT:',output)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--previous',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();setup(a.previous,a.output)
