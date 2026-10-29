"""Portable engineering checks. Raw exceptions remain in the evidence, never filtered away."""
import json,math,statistics
from pathlib import Path

def read_samples(path):
 if not Path(path).exists():return []
 return [json.loads(line) for line in Path(path).read_text().splitlines()]
def percentile(v,q):
 if not v:return None
 v=sorted(v);x=(len(v)-1)*q;i=int(x);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(x-i)
def distribution(v):return dict(count=len(v),min=min(v) if v else None,max=max(v) if v else None,mean=statistics.mean(v) if v else None,p50=percentile(v,.5),p95=percentile(v,.95))
def frequency(v,target,tolerance):
 valid=[x for x in v if x is not None and x>0];outside=[dict(index=i,value=x) for i,x in enumerate(v) if x is not None and x>0 and abs(x-target)>target*tolerance]
 return dict(target=target,distribution=distribution(valid),within_fraction=(len(valid)-len(outside))/len(valid) if valid else None,outside=outside,missing_or_gated=len(v)-len(valid),passed=len(valid)>=10 and (len(valid)-len(outside))/len(valid)>=.95)
def evaluate(samples,plan,phase='formal'):
 if not samples:return dict(passed=False,reason='no telemetry',sample_count=0)
 if phase=='idle':
  util=[x['gpu_util_pct'] for x in samples if x.get('gpu_util_pct') is not None];bg=[x['background_cpu_pct_one_core'] for x in samples];temps=[v for x in samples for k,v in x['temperatures_c'].items() if k in ('gpu','tj','cpu')]
  gpu=percentile(util,.95);background=percentile(bg,.95);temp=max(temps) if temps else None
  return dict(sample_count=len(samples),gpu_util_p95=gpu,background_cpu_p95_one_core=background,max_temperature_c=temp,passed=len(samples)>=130 and gpu is not None and gpu<=plan['idle_gpu_p95_max_pct'] and background<=plan['idle_background_cpu_p95_max_pct_one_core'] and temp is not None and temp<=plan['pre_worker_max_temperature_c'])
 active=[x for x in samples if x.get('gpu_util_pct') is not None and x['gpu_util_pct']>0]
 gpu=frequency([x['gpu_hz'] for x in active],plan['targets']['gpu_hz'],.01)
 emc=frequency([x['emc_hz'] for x in samples],plan['targets']['emc_hz'],.01)
 cpu=[]
 for i in range(6):
  values=[x['cpu_khz'][i] for x in samples if len(x.get('cpu_util_pct',[]))>i and x['cpu_util_pct'][i] is not None and x['cpu_util_pct'][i]>0]
  check=frequency(values,plan['targets']['cpu_khz'][str(i)] ,.01);check['core']=i
  # Some idle cores need not become active. Static min==max is also checked separately.
  if not values:check.update(passed=True,status='no_active_samples; static constraints required')
  elif len(values)<10:check['passed']=all(v is not None and v>0 and abs(v-plan['targets']['cpu_khz'][str(i)])<=.01*plan['targets']['cpu_khz'][str(i)] for v in values)
  cpu.append(check)
 bg=[x['background_cpu_pct_one_core'] for x in samples];bg_p95=percentile(bg,.95);temps=[v for x in samples for k,v in x['temperatures_c'].items() if k in ('gpu','tj','cpu')];max_temp=max(temps) if temps else None
 ages=[x['tegrastats_age_ms'] for x in samples if x.get('tegrastats_age_ms') is not None];fresh=sum(v<=250 for v in ages)/len(samples)
 outside_load=[dict(timestamp_ns=x['timestamp_ns'],background_cpu_pct=x['background_cpu_pct_one_core'],processes=x['top_background_processes']) for x in samples if x['background_cpu_pct_one_core']>plan['formal_background_cpu_p95_max_pct_one_core']]
 return dict(sample_count=len(samples),gpu_active_samples=len(active),gpu=gpu,emc=emc,cpu=cpu,background_cpu=distribution(bg),background_cpu_p95_limit=plan['formal_background_cpu_p95_max_pct_one_core'],load_exceptions=outside_load,max_temperature_c=max_temp,fresh_telemetry_fraction=fresh,passed=gpu['passed'] and emc['passed'] and all(x['passed'] for x in cpu) and bg_p95<=plan['formal_background_cpu_p95_max_pct_one_core'] and max_temp is not None and max_temp<=plan['formal_max_temperature_c'] and fresh>=.95)
