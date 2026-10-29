"""100ms host telemetry, actual CPU/GPU/EMC clocks, and interval CPU attribution.
Root is needed for read-only BPMP EMC access. No settings are changed here.
"""
import argparse,json,os,re,resource,signal,subprocess,threading,time
from pathlib import Path
GPU=Path('/sys/devices/platform/17000000.gpu');EMC=Path('/sys/kernel/debug/bpmp/debug/clk/emc/rate')
def read(p):
 try:return Path(p).read_text().strip()
 except OSError:return None
def number(p):
 try:return float(read(p))
 except (TypeError,ValueError):return None
def process_times():
 result={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   text=(p/'stat').read_text();right=text.rfind(')');fields=text[right+2:].split();ticks=int(fields[11])+int(fields[12]);cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
   result[int(p.name)]=(ticks,text[text.find('(')+1:right],cmd)
  except (OSError,ValueError,IndexError):continue
 return result
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output;started=time.monotonic();stop=threading.Event();latest=[None,None];samples=0;clock_ns=[]
 signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
 proc=subprocess.Popen(['/usr/bin/tegrastats','--interval','100'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
 def reader():
  with (out/'telemetry_raw.log').open('a',buffering=1) as f:
   for raw in proc.stdout:
    ts=time.time_ns();latest[:]=[ts,raw.rstrip()];gpu=read(GPU/'devfreq/17000000.gpu/cur_freq');f.write(f'{ts}\t{raw.rstrip()} GPU_CLOCK_HZ {gpu}\n')
 thread=threading.Thread(target=reader,daemon=True);thread.start();previous=process_times();previous_t=time.monotonic();hz=os.sysconf('SC_CLK_TCK');next_t=time.monotonic()
 with (out/'controls/frequency_load_samples.jsonl').open('a',buffering=1) as f:
  while not stop.is_set():
   now=time.monotonic();ts=time.time_ns();clock_start=time.perf_counter_ns()
   gpu_hz=number(GPU/'devfreq/17000000.gpu/cur_freq');emc_hz=number(EMC);cpus=[number(f'/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq') for i in range(6)];clock_ns.append(time.perf_counter_ns()-clock_start)
   curr=process_times();duration=max(.001,now-previous_t);background=worker=monitor=0.;top=[]
   for pid,(ticks,name,cmd) in curr.items():
    if pid not in previous:continue
    pct=max(0.,(ticks-previous[pid][0])/hz/duration*100)
    if '/src/benchmark.py' in cmd:worker+=pct
    elif pid==os.getpid() or name=='tegrastats':monitor+=pct
    else:
     background+=pct
     if pct>=1:top.append(dict(pid=pid,name=name,cpu_pct=pct))
   raw=latest[1] or '';m=re.search(r'GR3D_FREQ (\d+)%',raw);gpu_util=float(m[1]) if m else None;cpu_util=[]
   m=re.search(r'CPU \[([^]]*)\]',raw)
   if m:
    for v in m[1].split(','):
     x=re.match(r'(\d+)%',v);cpu_util.append(float(x[1]) if x else None)
   temps={name:float(v) for name,v in re.findall(r'(\w+)@([\d.]+)C',raw)}
   row=dict(timestamp_ns=ts,gpu_hz=gpu_hz,emc_hz=emc_hz,cpu_khz=cpus,cpu_util_pct=cpu_util,gpu_util_pct=gpu_util,temperatures_c=temps,tegrastats_age_ms=(ts-latest[0])/1e6 if latest[0] else None,background_cpu_pct_one_core=background,worker_cpu_pct_one_core=worker,monitor_cpu_pct_one_core=monitor,top_background_processes=sorted(top,key=lambda r:-r['cpu_pct'])[:12],frequency_read_wall_ns=clock_ns[-1],loadavg=read('/proc/loadavg'))
   f.write(json.dumps(row)+'\n');samples+=1;previous=curr;previous_t=now;next_t+=.1;stop.wait(max(0,next_t-time.monotonic()))
 proc.terminate();proc.wait(timeout=10);thread.join(timeout=5);own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN);wall=time.monotonic()-started
 report=dict(wall_seconds=wall,samples=samples,interval_ms=100,frequency_query_mean_wall_us=sum(clock_ns)/max(1,len(clock_ns))/1000,monitor_cpu_seconds=own.ru_utime+own.ru_stime,tegrastats_cpu_seconds=child.ru_utime+child.ru_stime,cpu_fraction_of_one_core=(own.ru_utime+own.ru_stime+child.ru_utime+child.ru_stime)/wall,note='Observed monitor CPU cost and clock-read wall cost; no controlled claim about benchmark perturbation.')
 (out/'controls/monitor_overhead.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
