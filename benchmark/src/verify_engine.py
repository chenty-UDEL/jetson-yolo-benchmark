"""Check reference versions and real TensorRT I/O before formal measurements."""
import torch
import tensorrt as trt
import ultralytics
from engine_inspector import inspect_engine
from common import *

def main():
    cfg=load(ROOT/'config.json');ref=load(ROOT/'reference_environment.json');mm=load(ROOT/'model_manifest.json');build=load(ROOT/'engine_build.json')
    assert torch.cuda.is_available()
    assert torch.__version__==ref['cuda_probe']['torch_version'],(torch.__version__,ref['cuda_probe']['torch_version'])
    assert trt.__version__==ref['packages']['tensorrt']
    assert ultralytics.__version__==ref['packages']['ultralytics']
    assert list(torch.cuda.get_device_capability())==ref['cuda_probe']['compute_capability']
    assert sha(ROOT/cfg['pt'])==mm['source_sha256']
    assert sha(ROOT/cfg['engine'])==build['engine_sha256']
    info=inspect_engine(ROOT/cfg['engine'])
    assert [1,3,640,640] in [x['shape'] for x in info['io'] if 'INPUT' in x['mode']]
    assert [1,84,8400] in [x['shape'] for x in info['io'] if 'OUTPUT' in x['mode']]
    assert build['flags']['half'] and not build['flags']['nms'] and not build['flags']['dynamic']
    save(ROOT/'engine_compatibility.json',dict(passed=True,engine_sha256=sha(ROOT/cfg['engine']),source_pt_sha256=sha(ROOT/cfg['pt']),torch=torch.__version__,tensorrt=trt.__version__,ultralytics=ultralytics.__version__,device=torch.cuda.get_device_name(),io=info['io'],note='FP16-enabled internal engine; actual I/O dtype retained. Engine is reused from controlled A.'))
    print('Engine and software verified for the original controlled Jetson environment')

if __name__=='__main__':main()
