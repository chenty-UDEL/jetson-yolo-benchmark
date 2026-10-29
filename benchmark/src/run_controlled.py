"""Authorized host administration and serial retest. All changed state restored in finally.
Run via sudo, with the password supplied to sudo interactively, never stored here.
"""
import argparse,datetime,glob,hashlib,json,os,signal,subprocess,sys,time,traceback,shutil
from pathlib import Path
from control_checks import read_samples,evaluate
DELIVERY=Path(__file__).resolve().parents[1];CONTROLS=None
GPU='/sys/devices/platform/17000000.gpu';EMC='/sys/kernel/debug/bpmp/debug/clk/emc';HALT='/sys/kernel/debug/bpmp/debug/bwmgr/bwmgr_halt'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def read(p):
 try:return Path(p).read_text().strip()
 except OSError as e:return {'error':str(e)}
def command(argv,log=None,check=True):
 r=subprocess.run(argv,capture_output=True,text=True)
 if log:Path(log).write_text(json.dumps(dict(command=argv,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
 if check and r.returncode:raise RuntimeError(f'{argv}: {r.returncode}: {r.stderr}')
 return r
def state():
 files=[]
 for policy in sorted(glob.glob('/sys/devices/system/cpu/cpufreq/policy*')):files += [policy+'/'+f for f in ['scaling_min_freq','scaling_max_freq','scaling_governor','scaling_available_frequencies']]
 files += glob.glob('/sys/devices/system/cpu/cpu[0-9]*/cpuidle/state*/disable')+glob.glob('/sys/devices/system/cpu/cpu[0-9]*/online')
 files += [GPU+'/devfreq/17000000.gpu/'+f for f in ['min_freq','max_freq','governor','available_frequencies']]+[GPU+'/railgate_enable',EMC+'/mrq_rate_locked',HALT,'/sys/kernel/nvpmodel_clk_cap/emc']
 files += glob.glob('/sys/class/thermal/thermal_zone*/policy')
 fan=glob.glob('/sys/devices/platform/pwm-fan*/hwmon/hwmon*/pwm*')
 return dict(timestamp_ns=time.time_ns(),static_values={p:read(p) for p in files},fan_pwm={p:read(p) for p in fan},emc_actual_hz=read(EMC+'/rate'),power=command(['/usr/sbin/nvpmodel','-q']).stdout.strip(),services={s:command(['systemctl','is-active',s],check=False).stdout.strip() for s in ['nvfancontrol','display-manager','ssh','NetworkManager']},model=read('/proc/device-tree/model').replace('\x00',' '))
def static_valid(plan):
 s=state();v=s['static_values'];problems=[]
 if s['power']!=plan['power_mode']:problems.append('power mode changed')
 for i in range(6):
  for field in ['scaling_min_freq','scaling_max_freq']:
   p=f'/sys/devices/system/cpu/cpu{i}/cpufreq/{field}'
   if float(read(p))!=plan['targets']['cpu_khz'][str(i)]:problems.append(p)
 for f in ['min_freq','max_freq']:
  if float(read(GPU+'/devfreq/17000000.gpu/'+f))!=plan['targets']['gpu_hz']:problems.append('gpu '+f)
 if read(EMC+'/mrq_rate_locked')!='1' or read(HALT)!='1':problems.append('EMC not fixed')
 if float(read('/sys/kernel/nvpmodel_clk_cap/emc'))!=plan['targets']['emc_hz']:problems.append('EMC cap differs')
 if s['services']['nvfancontrol']!=plan['fan_service']:problems.append('fan strategy changed')
 return dict(passed=not problems,problems=problems,state=s)
def freeze(root,container,plan):
 command(['docker','exec',container,'python3','/project/experiment_bundle/src/check_environment.py','--check-cuda','--expect-jetson','--output','/project/experiment_bundle/logs/container_environment.json'],root/'logs/preflight.json')
 env=json.loads((root/'logs/container_environment.json').read_text());env['jetson']['model']=read('/proc/device-tree/model').replace('\x00',' ').strip();env['host_control_state']=state();env['control_plan']=plan;env['container_identity']=command(['docker','inspect',container,'--format','{{.Image}} {{json .Mounts}}']).stdout.strip();save(root/'environment.json',env)
 c=json.loads((root/'config.json').read_text());c['manifest_sha256']=sha(root/'input_manifest.json');c['control_plan_sha256']=sha(CONTROLS/'control_plan.json');c['control_conditions_valid']=False;c['control_validation_source']='controls/control_validation.json';c['control_limitations']=['Pending evidence-based validation, not a manual approval flag'];save(root/'config.json',c);save(root/'controls/control_plan.json',plan)
 identity={name:sha(root/name) for name in ['config.json','environment.json','input_manifest.json','models/source_model.pt','models/source_model.engine','src/benchmark.py','src/common.py']};save(root/'execution_identity.json',identity)
 save(root/'engine_reuse.json',dict(reused_from='v2_controlled_original',engine_sha256=sha(root/'models/source_model.engine'),source_pt_sha256=sha(root/'models/source_model.pt'),new_build=False))
 assert identity['models/source_model.engine']=='2fa8248bba5ee2903ee6814d4592bbbb8118f4820adbc92df05a1e72f22e3413'
 assert identity['models/source_model.pt']=='0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
 assert identity['src/benchmark.py']=='268484b6b36a1eb46a5ee6b5e125f8067343ff99f493b04571b4462bf355bea1'
def run_experiment(root,container,plan):
 if (root/'run_manifest.json').exists():raise RuntimeError('Existing execution evidence; refuse overwrite. Use a new attempt directory.')
 manifest=json.loads((root/'input_manifest.json').read_text());assert len(manifest['frames'])==400
 c=json.loads((root/'config.json').read_text());runs=[];idle_records=[];save(root/'run_manifest.json',runs)
 monitor=subprocess.Popen([sys.executable,str(DELIVERY/'src/monitor.py'),'--output',str(root)],stdout=(root/'logs/monitor.log').open('w'),stderr=subprocess.STDOUT)
 try:
  for ri,order in enumerate(c['order'],1):
   for oi,backend in enumerate(order,1):
    rid=f'round_{ri:02d}';beg=time.time_ns();time.sleep(30);deadline=time.monotonic()+300
    while True:
     now=time.time_ns();samples=[x for x in read_samples(root/'controls/frequency_load_samples.jsonl') if now-15_000_000_000<=x['timestamp_ns']<=now]
     idle=evaluate(samples,plan,'idle');constraints=static_valid(plan)
     rec=dict(run_id=rid,backend=backend,cooldown_start_ns=beg,check_ns=now,actual_wait_seconds=(now-beg)/1e9,idle=idle,static=constraints);idle_records.append(rec);save(root/'controls/pre_worker_checks.json',idle_records)
     if idle['passed'] and constraints['passed']:break
     if time.monotonic()>deadline:raise RuntimeError(f'Pre-worker controls not met: {rid}/{backend}: {idle}')
     print('Additional cooldown / quiet wait:',rid,backend,json.dumps(idle),flush=True);time.sleep(5)
    load=command(['ps','-eo','user,pid,ppid,stat,pcpu,comm','--sort=-pcpu']).stdout;(root/'logs'/f'load_before_{rid}_{backend}.txt').write_text(load)
    record=dict(run_id=rid,backend=backend,backend_order=oi,start_ns=time.time_ns(),valid=False,pre_worker_check_index=len(idle_records)-1);runs.append(record);save(root/'run_manifest.json',runs)
    argv=['docker','exec',container,'python3','/project/experiment_bundle/src/benchmark.py','--backend',backend,'--run-id',rid,'--order',str(oi)]
    with (root/'logs'/f'formal_{rid}_{backend}.log').open('w') as log:r=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT)
    record.update(end_ns=time.time_ns(),exit_code=r.returncode)
    if r.returncode:record['invalid_reason']='worker failed; artifacts/logs retained';save(root/'run_manifest.json',runs);raise RuntimeError(f'Worker failed {rid}/{backend}')
    worker=json.loads((root/'runs'/rid/backend/'worker.json').read_text());record.update(worker)
    samples=[x for x in read_samples(root/'controls/frequency_load_samples.jsonl') if worker['measurement_start_ns']<=x['timestamp_ns']<=worker['measurement_end_ns']]
    checks=evaluate(samples,plan);checks['static_before']=constraints;checks['static_after']=static_valid(plan);checks['passed']=checks['passed'] and constraints['passed'] and checks['static_after']['passed'];record['controls_passed']=checks['passed'];save(root/'controls'/f'{rid}_{backend}.json',checks);save(root/'run_manifest.json',runs)
    print(root.parent.name,rid,backend,'controls',checks['passed'],'active_gpu_samples',checks['gpu_active_samples'],flush=True)
  all_checks={r['run_id']+'/'+r['backend']:json.loads((root/'controls'/f"{r['run_id']}_{r['backend']}.json").read_text()) for r in runs}
  valid=all(x['passed'] for x in all_checks.values()) and len(runs)==10;save(root/'controls/control_validation.json',dict(control_conditions_valid=valid,passed=valid,criteria=plan,per_run=all_checks))
 finally:
  monitor.terminate();monitor.wait(timeout=15)
  if not (root/'controls/control_validation.json').exists():save(root/'controls/control_validation.json',dict(control_conditions_valid=False,passed=False,reason='Execution incomplete or interrupted; see logs and pre-worker checks'))

def main():
 global CONTROLS
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--image',default='carkit-vesc-rplidar:local');a=p.parse_args()
 assert os.geteuid()==0,'Run with sudo on the Jetson'
 root=a.root.resolve();assert root.name=='experiment_bundle' and (root/'old_experiment_before.json').is_file()
 assert not (root/'run_manifest.json').exists(),'Existing attempt: refuse overwrite'
 CONTROLS=root/'controls';session=CONTROLS/f'session_{time.time_ns()}';session.mkdir(exist_ok=False)
 def interrupt(sig,frame):raise KeyboardInterrupt(f'signal {sig}')
 for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,interrupt)
 before=state();save(session/'before_state.json',before)
 assert 'Orin Nano' in before['model'],'Expected the original Orin Nano'
 assert '15W' in before['power'],'Keep the previous 15W mode; no automatic power-mode change'
 container='cisc662-coco400-'+str(time.time_ns())
 config=session/'jetson_clocks_before.conf';paused=[];applied=False;created=False;failed=None;restoration={}
 fan_status=Path.home()/'.jetsonclocks_fan.txt';fan_existed=fan_status.exists();fan_bytes=fan_status.read_bytes() if fan_existed else None
 try:
  command(['docker','image','inspect',a.image],root/'logs/image_inspect.json')
  command(['docker','run','-d','--name',container,'--runtime','nvidia','--network','none','--entrypoint','/bin/bash','-v',f'{root.parent}:/project','-w','/project/experiment_bundle',a.image,'-c','sleep infinity'],root/'logs/container_create.json');created=True
  print('HOST ROOT',root,'CONTAINER',container,flush=True)
  mount=command(['docker','inspect',container,'--format','{{json .Mounts}}']).stdout;print(mount,flush=True)
  mounts=json.loads(mount);assert any(Path(m['Source']).resolve()==root.parent and m['Destination']=='/project' for m in mounts)
  command(['docker','exec',container,'python3','/project/experiment_bundle/src/prepare_inputs.py'],root/'logs/prepare_inputs.json')
  command(['docker','exec',container,'python3','/project/experiment_bundle/src/check_environment.py','--check-cuda','--expect-jetson','--output','/project/experiment_bundle/environment.json'],root/'logs/preflight_initial.json')
  command(['docker','exec',container,'python3','/project/experiment_bundle/src/verify_engine.py'],root/'logs/verify_engine.json')
  for backend in ('pytorch_fp32','tensorrt_fp16'):
   command(['docker','exec',container,'python3','/project/experiment_bundle/src/benchmark.py','--backend',backend,'--run-id','preflight','--smoke'],root/'logs'/('smoke_'+backend+'.json'))
   smoke=json.loads((root/'smoke/preflight'/backend/'worker.json').read_text());assert smoke['measured_count']==8 and smoke['warmup_count']==50
  command(['/usr/bin/jetson_clocks','--show'],session/'before_show.json')
  command(['/usr/bin/jetson_clocks','--store',str(config)],session/'store.json');applied=True
  command(['/usr/bin/jetson_clocks'],session/'lock.json');command(['/usr/bin/jetson_clocks','--show'],session/'locked_show.json')
  uid=int(os.environ.get('SUDO_UID','1000'));allowed={'gnome-shell','gjs','rustdesk','update-manager','gnome-software'}
  for path in Path('/proc').glob('[0-9]*'):
   try:
    status=(path/'status').read_text().splitlines();owner=int(next(x for x in status if x.startswith('Uid:')).split()[1]);name=(path/'comm').read_text().strip();st=next(x for x in status if x.startswith('State:'))
    if owner==uid and name in allowed and '\tT' not in st and '\tt' not in st:
     pid=int(path.name);paused.append(dict(pid=pid,name=name,uid=owner,original_state=st));save(session/'paused_processes.json',paused);os.kill(pid,signal.SIGSTOP)
   except (OSError,ValueError,StopIteration):continue
  current=state();targets=dict(cpu_khz={str(i):float(read(f'/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_max_freq')) for i in range(6)},gpu_hz=float(read(GPU+'/devfreq/17000000.gpu/max_freq')),emc_hz=float(read('/sys/kernel/nvpmodel_clk_cap/emc')))
  assert all(abs(v-1510400)<=1 for v in targets['cpu_khz'].values()),targets
  assert abs(targets['gpu_hz']-624750000)<=1 and abs(targets['emc_hz']-2133000000)<=1,targets
  plan=dict(power_mode=before['power'],fan_service=before['services']['nvfancontrol'],targets=targets,frequency_tolerance_fraction=.01,required_in_tolerance_fraction=.95,gpu_active_definition='tegrastats GR3D utilization >0%; gated/missing retained',cpu_active_definition='per-core utilization >0%; static limits checked for all cores',idle_observation_seconds=15,minimum_cooldown_seconds=30,pre_worker_max_temperature_c=60,formal_max_temperature_c=70,idle_gpu_p95_max_pct=5,idle_background_cpu_p95_max_pct_one_core=75,formal_background_cpu_p95_max_pct_one_core=75,telemetry_interval_ms=100,background_rule='p95 other-process CPU <=75% of one core; exceptions retained; monitor measured separately',pause_rule='SIGSTOP current project user GUI/update whitelist only; resume exact PIDs in finally',session=str(session),clock_mechanism='Vendor jetson_clocks; same 15W maxima as A; no --fan and no nvpmodel change')
  save(CONTROLS/'control_plan.json',plan);save(session/'locked_state.json',current);assert static_valid(plan)['passed']
  freeze(root,container,plan);run_experiment(root,container,plan)
 except BaseException as e:
  failed=repr(e);(session/'failure.txt').write_text(traceback.format_exc());print(traceback.format_exc(),flush=True)
 finally:
  if applied:
   try:
    result=command(['/usr/bin/jetson_clocks','--restore',str(config)],session/'restore_command.json',check=False);restoration['vendor_restore_exit_code']=result.returncode
   except BaseException as e:restoration['vendor_restore_error']=repr(e)
  for entry in paused:
   try:os.kill(entry['pid'],signal.SIGCONT);entry['restored']=True
   except ProcessLookupError:entry['restored']=False;entry['reason']='process no longer exists'
  if fan_existed:fan_status.write_bytes(fan_bytes)
  elif fan_status.exists():fan_status.unlink()
  if created:command(['docker','stop','--time','1',container],root/'logs/container_stop.json',check=False)
  after=state();save(session/'after_state.json',after)
  differences={k:dict(before=v,after=after['static_values'].get(k)) for k,v in before['static_values'].items() if after['static_values'].get(k)!=v}
  restoration.update(paused_processes=paused,static_state_differences=differences,power_restored=before['power']==after['power'],fan_service_restored=before['services']['nvfancontrol']==after['services']['nvfancontrol'],failure=failed,passed=not differences and before['power']==after['power'] and before['services']['nvfancontrol']==after['services']['nvfancontrol'] and all(x.get('restored') for x in paused) and (not applied or restoration.get('vendor_restore_exit_code')==0))
  save(session/'restoration_log.json',restoration);save(CONTROLS/'restoration_log.json',restoration)
  uid=int(os.environ.get('SUDO_UID','0'));gid=int(os.environ.get('SUDO_GID','0'))
  # This newly created attempt only. No traversal or ownership changes in old data.
  for path in [root]+list(root.rglob('*')):
   if not path.is_symlink():
    try:os.chown(path,uid,gid)
    except OSError:pass
 if failed or not restoration['passed']:raise SystemExit(2)
 print('CONTROLLED COCO400 SESSION FINISHED; state restored',flush=True)

if __name__=='__main__':main()
