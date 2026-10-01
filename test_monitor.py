import importlib.util,json,pathlib,unittest,yaml,subprocess,copy
from unittest.mock import patch
P=pathlib.Path(__file__).parent
spec=importlib.util.spec_from_file_location('collector',P/'redis_docker_collect.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
INSPECT={'Id':'abc','State':{'Running':True},'RestartCount':2,'Mounts':[{'Type':'bind','Source':'/mnt/web-redis/data','Destination':'/data','RW':True}]}
INFO='redis_version:8.2.1\r\nused_memory:400\r\nmaxmemory:1000\r\nconnected_clients:2\r\nmaxclients:10\r\nkeyspace_hits:8\r\nkeyspace_misses:2\r\naof_enabled:1\r\naof_last_write_status:ok\r\n'
def fake(args,**kw):
 if 'inspect' in args:return json.dumps([INSPECT])
 if args[-1]=='PING':return 'PONG'
 if args[-1]=='INFO':return INFO
 if args[-3:]==['CONFIG','GET','dir']:return 'dir\n/data'
 if 'CONFIG' in args and '--json' in args:return json.dumps({'dir':'/data','maxmemory':'1000','appendonly':'yes'})
 raise AssertionError(args)
class CollectorTests(unittest.TestCase):
 def setUp(self):
  self.ps=[patch.object(c,'run',side_effect=fake),patch.object(c.os.path,'ismount',return_value=False),patch.object(c.pathlib.Path,'exists',return_value=False)]
  for p in self.ps:p.start();self.addCleanup(p.stop)
 def test_disabled_discovery_reads_nothing(self):
  with patch.object(c.pathlib.Path,'iterdir',side_effect=AssertionError('must not read')):
   self.assertEqual(c.discover('network','0','1'),[])
   self.assertEqual(c.discover('disk','1','0'),[])
 def test_enabled_discovery(self):
  with patch.object(c.pathlib.Path,'iterdir',return_value=[pathlib.Path('/sys/block/sdb')]):
   self.assertEqual(c.discover('disk','1','1'),[{'{#DEVNAME}':'sdb'}])
 def test_healthy(self):
  d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertEqual(d['collector_ok'],1);self.assertEqual(d['memory_used_pct'],40);self.assertEqual(d['hit_ratio'],80);self.assertEqual(d['bind_ok'],1)
 def test_absent_mount_no_fake_filesystem(self):
  d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertEqual(d['mount_ok'],0);self.assertNotIn('fs_used_pct',d)
 def test_wrong_redis_dir(self):
  def call(args,**kw):return 'dir\n/tmp' if args[-3:]==['CONFIG','GET','dir'] else fake(args,**kw)
  with patch.object(c,'run',side_effect=call):d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379')
  self.assertEqual(d['bind_ok'],0)
 def test_wrong_mount(self):
  obj=copy.deepcopy(INSPECT);obj['Mounts'][0]['Source']='/other'
  with patch.object(c,'run',side_effect=lambda args,**kw:json.dumps([obj]) if 'inspect' in args else fake(args,**kw)):
   self.assertEqual(c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379')['bind_ok'],0)
 def test_auth_denied(self):
  with patch.object(c,'run',side_effect=lambda args,**kw:'NOAUTH Authentication required.' if args[-1]=='PING' else fake(args,**kw)):
   d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertEqual(d['ping_ok'],0);self.assertEqual(d['collector_ok'],0)
 def test_info_denied(self):
  with patch.object(c,'run',side_effect=lambda args,**kw:'NOPERM' if args[-1]=='INFO' else fake(args,**kw)):
   d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertEqual(d['ping_ok'],1);self.assertEqual(d['collector_ok'],0)
 def test_missing_container(self):
  def call(args,**kw):
   if 'version' in args:return '28.0'
   raise RuntimeError('command failed')
  with patch.object(c,'run',side_effect=call):
   d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertEqual(d['docker_ok'],1);self.assertEqual(d['container_running'],0)
 def test_docker_unavailable(self):
  with patch.object(c,'run',side_effect=RuntimeError('failed')):
   self.assertEqual(c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379')['docker_ok'],0)
 def test_container_stopped(self):
  obj=copy.deepcopy(INSPECT);obj['State']['Running']=False
  with patch.object(c,'run',return_value=json.dumps([obj])):
   d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertEqual(d['ping_ok'],0)
 def test_zero_maxmemory_aof_off(self):
  with patch.object(c,'run',side_effect=lambda args,**kw:INFO.replace('maxmemory:1000','maxmemory:0').replace('aof_enabled:1','aof_enabled:0') if args[-1]=='INFO' else fake(args,**kw)):
   d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379');self.assertNotIn('memory_used_pct',d);self.assertNotIn('aof_current_size',d['info'])
 def test_reject_bad_arguments(self):
  for args in [('redis;id','/mnt/d','/mnt','6379'),('redis','/mnt/../data','/mnt','6379'),('redis','/mnt/data','/','6379'),('redis','/other/data','/mnt','6379'),('redis','/mnt/data','/mnt','70000')]:
   with self.assertRaises(ValueError):c.validate(*args)
 def test_password_not_in_arguments(self):
  calls=[]
  def call(args,**kw):calls.append((args,kw));return fake(args,**kw)
  with patch.object(c.pathlib.Path,'exists',return_value=True),patch.object(c.pathlib.Path,'read_text',return_value='{"username":"monitor","password":"secret_test"}'),patch.object(c,'run',side_effect=call):
   c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379')
  self.assertNotIn('secret_test',str([a for a,k in calls]));self.assertTrue(any(k.get('env',{}).get('REDISCLI_AUTH')=='secret_test' for a,k in calls))
class TemplateTests(unittest.TestCase):
 def test_yaml_and_lld_gates(self):
  for version in ['6_2','7_0','7_4']:
   doc=yaml.safe_load((P/f'template_redis_docker_passive_{version}.yaml').read_text())['zabbix_export'];t=doc['templates'][0]
   macros={m['macro']:m['value'] for m in t['macros']}
   self.assertEqual(macros['{$REDIS.HOST.ENABLED}'],'0')
   allitems=t['items']+[i for r in t['discovery_rules'] for i in r['item_prototypes']]
   self.assertTrue(all(i['type'] in ['ZABBIX_PASSIVE','DEPENDENT','CALCULATED'] for i in allitems))
   for r in t['discovery_rules']:
    if not r['name'].startswith('Redis host:'):continue
    self.assertTrue(all('{#' in i['key'] for i in r['item_prototypes']))
    code=r['preprocessing'][0]['parameters'][0]
    for macro,value in macros.items():code=code.replace(macro,value)
    output=subprocess.check_output(['node','-e','console.log((new Function("value",'+json.dumps(code)+'))("[]"))'],text=True).strip();self.assertEqual(output,'[]')
    on=r['preprocessing'][0]['parameters'][0]
    for macro,value in macros.items():on=on.replace(macro,'1' if 'ENABLED' in macro else value)
    if r['type']=='DEPENDENT':
     output=subprocess.check_output(['node','-e','console.log((new Function("value",'+json.dumps(on)+'))("{}"))'],text=True).strip();self.assertEqual(json.loads(output)[0]['{#CPU}'],'all')
   # JSONPaths refer to real collector fields; raw missing optional fields discard.
   keys=[i['key'] for i in allitems];self.assertEqual(len(keys),len(set(keys)))
   for i in t['items']:
    if i['type']=='DEPENDENT':self.assertEqual(i['preprocessing'][0]['error_handler'],'DISCARD_VALUE')
 def test_disk_counter_extraction(self):
  doc=yaml.safe_load((P/'template_redis_docker_passive_6_2.yaml').read_text())
  disk=next(r for r in doc['zabbix_export']['templates'][0]['discovery_rules'] if r['key'].startswith('rdm.disk.discovery'))
  for i in disk['item_prototypes']:
   if i['type']=='DEPENDENT':
    code=i['preprocessing'][0]['parameters'][0]
    value=subprocess.check_output(['node','-e','console.log((new Function("value",'+json.dumps(code)+'))("100 2 300 400 500 6 700 800 0 900 1000"))'],text=True).strip()
    expected=100 if '.read.ops[' in i['key'] else 400 if '.read.time[' in i['key'] else 500 if '.write.ops[' in i['key'] else 800
    self.assertEqual(float(value),expected)
class EnrichmentTests(unittest.TestCase):
 def run_collect(self,info=INFO,config=None):
  def call(args,**kw):
   if args[-1]=='INFO':return info
   if 'CONFIG' in args and '--json' in args and config is not None:return json.dumps(config)
   return fake(args,**kw)
  with patch.object(c,'run',side_effect=call),patch.object(c.os.path,'ismount',return_value=False),patch.object(c.pathlib.Path,'exists',return_value=False):
   return c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379')
 def test_database_and_replica_parsing(self):
  d=self.run_collect(INFO+'db0:keys=10,expires=3,avg_ttl=1200\nmaster_repl_offset:1000\nslave0:ip=10.0.0.2,port=6379,state=online,offset=750,lag=2\n')
  self.assertEqual(d['databases']['db0'],{'keys':10,'expires':3,'avg_ttl':1200})
  self.assertEqual(d['replicas']['10.0.0.2:6379']['lag_bytes'],250)
 def test_empty_database_list(self):self.assertEqual(self.run_collect()['db_discovery'],[])
 def test_config_whitelist(self):
  d=self.run_collect(config={'dir':'/data','requirepass':'SECRET','masterauth':'SECRET','maxmemory':'1000'})
  self.assertNotIn('SECRET',json.dumps(d));self.assertEqual(d['config_snapshot_ok'],1)
 def test_config_failure_does_not_break_primary(self):
  d=self.run_collect(config='NOPERM');self.assertEqual(d['collector_ok'],1);self.assertEqual(d['config_snapshot_ok'],0)
 def test_resp2_config_json(self):
  d=self.run_collect(config=['dir','/data','appendonly','yes']);self.assertEqual(json.loads(d['config_snapshot'])['appendonly'],'yes')
 def test_redis6_base_still_works(self):
  d=self.run_collect(INFO.replace('8.2.1','6.2.6'));self.assertEqual(d['collector_ok'],1);self.assertEqual(d['config_snapshot_ok'],0)
 def test_ping_timeout_keeps_docker_and_disk_status(self):
  def call(args,**kw):
   if args[-1]=='PING':raise subprocess.TimeoutExpired('docker',2)
   return fake(args,**kw)
  with patch.object(c,'run',side_effect=call),patch.object(c.os.path,'ismount',return_value=False),patch.object(c.pathlib.Path,'exists',return_value=False):
   d=c.collect('redis','/mnt/web-redis/data','/mnt/web-redis','6379')
  self.assertEqual(d['docker_ok'],1);self.assertEqual(d['container_running'],1);self.assertEqual(d['ping_ok'],0)
 def test_slowlog_off_makes_no_calls(self):
  with patch.object(c,'run',side_effect=AssertionError('no call')):self.assertEqual(c.slowlog_collect('redis','6379','0'),{'enabled':0,'ok':1})
 def test_slowlog_exports_no_query_arguments(self):
  def call(args,**kw):return '128' if args[-1]=='LEN' else json.dumps([[9999,1000000,20000,['SET','password','SECRET'],'10.0.0.1','client']])
  with patch.object(c,'run',side_effect=call),patch.object(c.pathlib.Path,'exists',return_value=False):d=c.slowlog_collect('redis','6379','1')
  self.assertEqual(d['last_id'],9999);self.assertEqual(d['length'],128);self.assertNotIn('SECRET',json.dumps(d))
 def test_slowlog_permission_denied(self):
  with patch.object(c,'run',return_value='"NOPERM"'),patch.object(c.pathlib.Path,'exists',return_value=False):self.assertEqual(c.slowlog_collect('redis','6379','1')['ok'],0)
 def test_preserves_old_items_and_uuid(self):
  old=yaml.safe_load((P/'tests'/'baseline_v1_0_0.yaml').read_text())['zabbix_export']['templates'][0]
  new=yaml.safe_load((P/'template_redis_docker_passive_6_2.yaml').read_text())['zabbix_export']['templates'][0]
  index={i['key']:i['uuid'] for i in new['items']}
  for i in old['items']:self.assertEqual(index[i['key']],i['uuid'])
 def test_uuid_macros_graphs_dependencies(self):
  import re
  for version in ['6_2','7_0','7_4']:
   d=yaml.safe_load((P/f'template_redis_docker_passive_{version}.yaml').read_text())['zabbix_export'];t=d['templates'][0]
   def walk(x):
    if isinstance(x,dict):
     if 'uuid' in x:self.assertRegex(x['uuid'],r'^[0-9a-f]{32}$')
     for v in x.values():walk(v)
    elif isinstance(x,list):
     for v in x:walk(v)
   walk(d)
   declared={m['macro'] for m in t['macros']}
   self.assertTrue(set(re.findall(r'\{\$REDIS\.[A-Z0-9.]+\}',json.dumps(d)))<=declared)
   keys={i['key'] for i in t['items']}|{i['key'] for r in t['discovery_rules'] for i in r['item_prototypes']}
   graphs=d['graphs']+[g for r in t['discovery_rules'] for g in r.get('graph_prototypes',[])]
   for g in graphs:
    for gi in g['graph_items']:self.assertIn(gi['item']['key'],keys)
   graphnames={g['name'] for g in d['graphs']}
   for widget in t['dashboards'][0]['pages'][0]['widgets']:
    for field in widget['fields']:
     if field['type']=='GRAPH':self.assertIn(field['value']['name'],graphnames)
    self.assertLessEqual(int(widget['x'])+int(widget['width']),24 if version=='6_2' else 72)
   expressions={tr['expression']:tr for tr in d['triggers']}
   for tr in d['triggers']:
    for dep in tr.get('dependencies',[]):self.assertIn(dep['expression'],expressions)
   def visit(ex,path):
    self.assertNotIn(ex,path)
    for dep in expressions[ex].get('dependencies',[]):visit(dep['expression'],path+[ex])
   for ex in expressions:visit(ex,[])
 def test_database_lld_retains_resources_on_failure(self):
  d=yaml.safe_load((P/'template_redis_docker_passive_6_2.yaml').read_text())
  rule=next(r for r in d['zabbix_export']['templates'][0]['discovery_rules'] if r['key']=='rdm.db.discovery')
  code=rule['preprocessing'][0]['parameters'][0]
  payload=json.dumps({'collector_ok':1,'db_discovery':[{'{#DB}':'db0'}]})
  out=subprocess.check_output(['node','-e','console.log((new Function("value",'+json.dumps(code)+'))('+json.dumps(payload)+'))'],text=True)
  self.assertEqual(json.loads(out),[{'{#DB}':'db0'}])
  out=subprocess.run(['node','-e','(new Function("value",'+json.dumps(code)+'))("{}")'],capture_output=True)
  self.assertNotEqual(out.returncode,0)
if __name__=='__main__':unittest.main(verbosity=2)

