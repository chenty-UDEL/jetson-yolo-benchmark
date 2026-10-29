"""One isolated worker. Shared preprocessing/NMS; all serialization outside timing."""
import argparse,os,resource,time
import cv2,numpy as np,torch
from ultralytics.nn.autobackend import AutoBackend
from ultralytics.data.augment import LetterBox
from ultralytics.utils import nms,ops
from common import *

def main():
 p=argparse.ArgumentParser();p.add_argument('--backend',choices=['pytorch_fp32','tensorrt_fp16'],required=True);p.add_argument('--run-id',required=True);p.add_argument('--order',type=int,default=1);p.add_argument('--smoke',action='store_true');args=p.parse_args()
 c=load(ROOT/'config.json');manifest=load(ROOT/'input_manifest.json')
 if sha(ROOT/'input_manifest.json')!=c['manifest_sha256']:raise RuntimeError('Manifest changed')
 mm=load(ROOT/'model_manifest.json');eb=load(ROOT/'engine_build.json')
 assert sha(ROOT/c['pt'])==mm['source_sha256'];assert sha(ROOT/c['engine'])==eb['engine_sha256']
 torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 torch.backends.cudnn.benchmark=False;torch.backends.cudnn.deterministic=False
 torch.set_grad_enabled(False)
 device=torch.device('cuda:0'); ispt=args.backend=='pytorch_fp32'
 model=AutoBackend(str(ROOT/c['pt' if ispt else 'engine']),device=device,fp16=not ispt,fuse=True,verbose=False)
 if ispt:
  model.model.eval();model.model.float()
  assert all(x.dtype==torch.float32 for x in model.model.parameters())
 dtype=torch.float16 if model.fp16 else torch.float32
 lb=LetterBox(new_shape=(640,640),auto=False,scale_fill=False,scaleup=True,stride=32)
 frames=[manifest['frames'][i] for i in np.linspace(0,len(manifest['frames'])-1,8,dtype=int)] if args.smoke else manifest['frames']
 images=[]
 for f in frames:
  path=ROOT/f['path'];assert sha(path)==f['file_sha256'];im=cv2.imread(str(path));assert im is not None
  assert hashlib.sha256(im.tobytes()).hexdigest()==f['pixel_sha256'];images.append(im)
 torch.cuda.reset_peak_memory_stats();warm=[];rows=[];dets=[]
 def step(im):
  torch.cuda.synchronize(device);wall_start=time.time_ns();start=time.perf_counter_ns()
  a=lb(image=im);a=np.ascontiguousarray(a[:,:,::-1].transpose(2,0,1));x=torch.from_numpy(a).to(device=device,dtype=dtype).unsqueeze(0)/255.
  assert list(x.shape)==c['shape'];torch.cuda.synchronize(device);t1=time.perf_counter_ns()
  pred=model(x);torch.cuda.synchronize(device);t2=time.perf_counter_ns()
  if isinstance(pred,(list,tuple)):pred=pred[0]
  # Raw (B,4+nc,N), no embedded NMS; same FP32 conversion and NMS on GPU.
  assert pred.ndim==3 and pred.shape[1]==4+len(model.names),list(pred.shape)
  pred=pred.float()
  result=nms.non_max_suppression(pred,conf_thres=c['confidence'],iou_thres=c['nms_iou'],classes=c['classes'],agnostic=False,max_det=c['max_det'],nc=len(model.names))[0]
  result[:,:4]=ops.scale_boxes(x.shape[2:],result[:,:4],im.shape)
  out=result.cpu();torch.cuda.synchronize(device);t3=time.perf_counter_ns();wall_end=time.time_ns()
  return dict(preprocess_ms=(t1-start)/1e6,inference_ms=(t2-t1)/1e6,postprocess_ms=(t3-t2)/1e6,total_ms=(t3-start)/1e6,start_unix_ns=wall_start,end_unix_ns=wall_end),out
 with torch.inference_mode(),torch.autocast(device_type='cuda',enabled=False):
  for i in range(c['warmup']):
   timing,_=step(images[i%len(images)]);warm.append(dict(index=i,**timing))
  measure_start=time.time_ns()
  for f,im in zip(frames,images):
   timing,out=step(im)
   rows.append(dict(experiment_id=c['experiment_id'],run_id=args.run_id,backend=args.backend,backend_order=args.order,frame_id=f['frame_id'],input_shape='1x3x640x640',input_dtype=str(dtype),**timing))
   dets.append(dict(run_id=args.run_id,backend=args.backend,frame_id=f['frame_id'],width=f['width'],height=f['height'],classes=c['classes'],boxes=out.tolist()))
  measure_end=time.time_ns()
 dest=ROOT/('smoke' if args.smoke else 'runs')/args.run_id/args.backend
 dest.mkdir(parents=True,exist_ok=False)
 csvout(dest/'measurements.csv',rows)
 with open(dest/'detections.jsonl','w') as stream:
  for d in dets:stream.write(json.dumps(d)+'\n')
 save(dest/'warmup.json',warm)
 save(dest/'worker.json',dict(run_id=args.run_id,backend=args.backend,backend_order=args.order,measurement_start_ns=measure_start,measurement_end_ns=measure_end,warmup_count=len(warm),measured_count=len(rows),pid=os.getpid(),max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(),precision=dict(dtype=str(dtype),tf32_matmul=torch.backends.cuda.matmul.allow_tf32,tf32_cudnn=torch.backends.cudnn.allow_tf32,amp=False,fused=True),config_sha256=sha(ROOT/'config.json'),environment_sha256=sha(ROOT/'environment.json'),source_sha256=sha(__file__),valid=True,exit_code=0))
 print(json.dumps(dict(run=args.run_id,backend=args.backend,frames=len(rows),inference_p50=float(np.median([r['inference_ms'] for r in rows])))),flush=True)
if __name__=='__main__':main()
