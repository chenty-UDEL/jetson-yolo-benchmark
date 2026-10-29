"""CPU-only deterministic same-class IoU-descending greedy backend agreement."""
from collections import defaultdict
from common import *
def iou(a,b):
 x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]));inter=x*y
 union=max(0,a[2]-a[0])*max(0,a[3]-a[1])+max(0,b[2]-b[0])*max(0,b[3]-b[1])-inter
 return inter/union if union else 0.
def pair(a,b,threshold=.5):
 candidates=sorted([(-iou(x,y),i,j) for i,x in enumerate(a) for j,y in enumerate(b) if int(x[5])==int(y[5]) and iou(x,y)>=threshold])
 used_a=set();used_b=set();matches=[]
 for neg,i,j in candidates:
  if i not in used_a and j not in used_b:
   used_a.add(i);used_b.add(j);matches.append((i,j,-neg,abs(a[i][4]-b[j][4])))
 return matches,[i for i in range(len(a)) if i not in used_a],[j for j in range(len(b)) if j not in used_b]
def metrics(tp,fp,fn,ious,diffs):
 den=2*tp+fp+fn
 return dict(TP=tp,FP=fp,FN=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,F1=2*tp/den if den else None,mean_matched_iou=sum(ious)/len(ious) if ious else None,mean_abs_confidence_difference=sum(diffs)/len(diffs) if diffs else None,status='evaluable' if den else 'not_evaluable')
def compare(root=ROOT):
 c=load(root/'config.json');data={}
 with open(root/'detections.jsonl',encoding='utf-8') as f:
  for line in f:
   d=json.loads(line);key=(d['run_id'],d['frame_id'],d['backend'])
   if key in data:raise ValueError('Duplicate detection key')
   data[key]=d
 groups=defaultdict(lambda:dict(tp=0,fp=0,fn=0,ious=[],diffs=[]));records=[];differences=[]
 for run,fid in sorted({(r,f) for r,f,_ in data}):
  a=data[(run,fid,'pytorch_fp32')]['boxes'];b=data[(run,fid,'tensorrt_fp16')]['boxes']
  matches,ua,ub=pair(a,b,c['match_iou'])
  for category in c['classes']:
   m=[v for v in matches if int(a[v[0]][5])==category];fn=sum(int(a[i][5])==category for i in ua);fp=sum(int(b[j][5])==category for j in ub)
   for key in [(run,str(category)),('pooled',str(category)),(run,'all'),('pooled','all')]:
    g=groups[key];g['tp']+=len(m);g['fp']+=fp;g['fn']+=fn;g['ious'] += [v[2] for v in m];g['diffs'] += [v[3] for v in m]
  for i,j,overlap,diff in matches:records.append(dict(run_id=run,frame_id=fid,class_id=int(a[i][5]),status='matched',pt_index=i,trt_index=j,iou=overlap,abs_confidence_difference=diff))
  for i in ua:records.append(dict(run_id=run,frame_id=fid,class_id=int(a[i][5]),status='unmatched_pt',pt_index=i,trt_index=None,iou=None,abs_confidence_difference=None))
  for j in ub:records.append(dict(run_id=run,frame_id=fid,class_id=int(b[j][5]),status='unmatched_trt',pt_index=None,trt_index=j,iou=None,abs_confidence_difference=None))
  if ua or ub:differences.append(dict(run_id=run,frame_id=fid,unmatched_pt=len(ua),unmatched_trt=len(ub)))
 result={f'{run}/{category}':metrics(g['tp'],g['fp'],g['fn'],g['ious'],g['diffs']) for (run,category),g in groups.items()}
 pooled=result.get('pooled/all',metrics(0,0,0,[],[]))
 result['targets']=dict(F1=pooled['F1']>=.95 if pooled['F1'] is not None else None,mean_matched_iou=pooled['mean_matched_iou']>=.90 if pooled['mean_matched_iou'] is not None else None,mean_abs_confidence_difference=pooled['mean_abs_confidence_difference']<=.05 if pooled['mean_abs_confidence_difference'] is not None else None)
 result['all_target_classes_evaluable']=all(result.get('pooled/'+str(cls),{}).get('status')=='evaluable' for cls in c['classes'])
 result['acceptance_status']=('not_evaluable_for_all_target_classes' if not result['all_target_classes_evaluable'] else ('passed' if all(v is True for v in result['targets'].values()) else 'failed'))
 csvout(root/'matches.csv',records,['run_id','frame_id','class_id','status','pt_index','trt_index','iou','abs_confidence_difference'])
 save(root/'agreement.json',result);save(root/'samples/differences.json',differences)
 return result
if __name__=='__main__':compare()
