import yaml,uuid, pathlib,sys,hashlib
P=pathlib.Path(__file__).parent
T='Redis Docker on Debian by passive agent'
def uid(s):return uuid.UUID(bytes=hashlib.sha256(('redis-docker-monitor/v1/'+s).encode()).digest()[:16],version=4).hex
def tags(c):return [{'tag':'component','value':c}]
def item(name,key,typ='UNSIGNED',comp='redis'):
 return dict(uuid=uid(key),name=name,type='ZABBIX_PASSIVE',key=key,delay='1m',history='7d',trends='365d',value_type=typ,tags=tags(comp))
macros={'CONTAINER':'redis','DATA.PATH':'/mnt/web-redis/data','MOUNT.PATH':'/mnt/web-redis','PORT':'6379','HOST.ENABLED':'0','HOST.CPU.ENABLED':'1','HOST.MEMORY.ENABLED':'1','HOST.SWAP.ENABLED':'1','HOST.NETWORK.ENABLED':'0','HOST.IF.REGEX':'^(eth[0-9]+|en[a-zA-Z0-9]+)$','AOF.REQUIRED':'1','EVICTION.ALERT':'0','MEMORY.WARN':'80','DISK.WARN':'75','DISK.CRIT':'90','CLIENTS.WARN':'80','HOST.CPU.WARN':'90','HOST.MEMORY.WARN':'90','HOST.SWAP.WARN':'20','HOST.DISK.ENABLED':'0','HOST.DEV.REGEX':'^(sd[a-z]+|vd[a-z]+|nvme[0-9]+n[0-9]+)$','HOST.DISK.LATENCY.WARN':'50'}
masterkey='rdm.collect["{$REDIS.CONTAINER}","{$REDIS.DATA.PATH}","{$REDIS.MOUNT.PATH}","{$REDIS.PORT}"]'
master=item('Redis Docker: collector JSON',masterkey,'TEXT','collector');master.update(history='1d',trends='0')
items=[master]
metrics=[('collector_ok','Collector successful','UNSIGNED','collector'),('docker_ok','Docker API reachable','UNSIGNED','docker'),('container_running','Container running','UNSIGNED','docker'),('container_restarts','Container restart count','UNSIGNED','docker'),('container_health','Container health (none if not configured)','CHAR','docker'),('container_id','Container ID','CHAR','docker'),('ping_ok','Redis PING successful','UNSIGNED','redis'),('redis_ms','Redis PING latency','FLOAT','redis'),('mount_ok','Required filesystem mounted','UNSIGNED','filesystem'),('bind_ok','Expected writable bind mount to /data','UNSIGNED','filesystem'),('fs_readonly','Filesystem read only','UNSIGNED','filesystem'),('fs_used_pct','Filesystem used','FLOAT','filesystem'),('inode_used_pct','Inodes used','FLOAT','filesystem'),('fs_free','Filesystem available bytes','UNSIGNED','filesystem'),('error','Collector error','TEXT','collector')]
info_nums='uptime_in_seconds connected_clients blocked_clients maxclients rejected_connections used_memory used_memory_rss maxmemory evicted_keys expired_keys keyspace_hits keyspace_misses instantaneous_ops_per_sec total_commands_processed total_connections_received latest_fork_usec rdb_last_save_time rdb_changes_since_last_save aof_enabled aof_rewrite_in_progress aof_current_size aof_base_size aof_delayed_fsync loading'.split()
metrics += [('info.'+k,k.replace('_',' '),'UNSIGNED','redis') for k in info_nums]
metrics += [('info.mem_fragmentation_ratio','Memory fragmentation ratio','FLOAT','redis')]
metrics += [('info.'+k,k.replace('_',' '),'CHAR','persistence') for k in ['rdb_last_bgsave_status','aof_last_write_status','aof_last_bgrewrite_status','redis_version','role']]
metrics += [('memory_used_pct','Redis maxmemory used (only if maxmemory > 0)','FLOAT','redis'),('clients_used_pct','Redis maxclients used','FLOAT','redis'),('hit_ratio','Cache hit ratio, lifetime','FLOAT','redis')]
for field,name,typ,comp in metrics:
 i=item('Redis Docker: '+name,'rdm.'+field,typ,comp);i.update(type='DEPENDENT',delay='0',master_item={'key':masterkey},preprocessing=[{'type':'JSONPATH','parameters':['$.'+field],'error_handler':'DISCARD_VALUE'}])
 if typ in ['TEXT','CHAR']:i['trends']='0'
 if field.endswith('_pct') or field=='hit_ratio':i['units']='%'
 if field in ['fs_free','info.used_memory','info.used_memory_rss','info.maxmemory','info.aof_current_size','info.aof_base_size']:i['units']='B'
 if field=='redis_ms':i['units']='ms'
 items.append(i)
def expr(key,fn='last',arg=''):return f'{fn}(/{T}/{key}{","+arg if arg else ""})'
def trig(key,name,ex,severity='WARNING'):
 return {'uuid':uid('trigger/'+key),'expression':ex,'name':name,'priority':severity,'tags':tags('redis-docker')}
triggers=[trig('nodata','Redis Docker: no collector data',expr(masterkey,'nodata','5m')+'=1','HIGH')]
for key,name,sev in [('collector_ok','collection failed','WARNING'),('docker_ok','Docker API unavailable','HIGH'),('container_running','container stopped or missing','HIGH'),('ping_ok','Redis PING failed','HIGH'),('mount_ok','required filesystem missing','DISASTER'),('bind_ok','/data bind mount mismatch or not writable','HIGH')]:
 triggers.append(trig(key,'Redis Docker: '+name,expr('rdm.'+key,'max','3m')+'=0',sev))
triggers += [trig('readonly','Redis Docker: data filesystem read only',expr('rdm.fs_readonly')+'=1','HIGH'),trig('health','Redis Docker: container unhealthy',expr('rdm.container_health')+'="unhealthy"','HIGH'),trig('restarts','Redis Docker: container restarted',expr('rdm.container_restarts','change')+'>0'),trig('recreate','Redis Docker: container recreated',expr('rdm.container_id','change')+'=1','INFO')]
for k,n in [('fs_used_pct','data filesystem'),('inode_used_pct','inodes')]:
 triggers += [trig(k+'crit','Redis Docker: '+n+' usage critical',expr('rdm.'+k,'min','5m')+'>{$REDIS.DISK.CRIT}','HIGH'),trig(k+'warn','Redis Docker: '+n+' usage high',expr('rdm.'+k,'min','5m')+'>{$REDIS.DISK.WARN} and '+expr('rdm.'+k,'max','5m')+'<={$REDIS.DISK.CRIT}')]
for k in ['aof_last_write_status','aof_last_bgrewrite_status','rdb_last_bgsave_status']:
 triggers.append(trig(k,'Redis Docker: '+k+' is err',expr('rdm.info.'+k)+'="err"' + (' and '+expr('rdm.info.aof_enabled')+'=1' if k.startswith('aof_') else ''),'HIGH'))
triggers += [trig('aof','Redis Docker: required AOF disabled','{$REDIS.AOF.REQUIRED}=1 and '+expr('rdm.info.aof_enabled')+'=0','HIGH'),trig('evictions','Redis Docker: keys evicted','{$REDIS.EVICTION.ALERT}=1 and '+expr('rdm.info.evicted_keys','change')+'>0'),trig('reject','Redis Docker: rejected connections increased',expr('rdm.info.rejected_connections','change')+'>0'),trig('fsync','Redis Docker: delayed AOF fsync increased',expr('rdm.info.aof_delayed_fsync','change')+'>0'),trig('memory','Redis Docker: maxmemory usage high',expr('rdm.memory_used_pct','min','5m')+'>{$REDIS.MEMORY.WARN}'),trig('clients','Redis Docker: clients near maxclients',expr('rdm.clients_used_pct','min','5m')+'>{$REDIS.CLIENTS.WARN}')]
# Singleton LLD on agent.ping. Filtering returns no entities when host collection is disabled.
rules=[]
for group,keys in {'CPU':[('CPU utilization','system.cpu.util[{#CPU},idle]','FLOAT','%',True),('Load average 1m','system.cpu.load[{#CPU},avg1]','FLOAT','',False)],'MEMORY':[('Memory used','vm.memory.size[{#PAVAILABLE}]','FLOAT','%',True),('Available memory','vm.memory.size[{#AVAILABLE}]','UNSIGNED','B',False)],'SWAP':[('Swap used','system.swap.size[{#CPU},pused]','FLOAT','%',False)]}.items():
 prototypes=[]
 for name,key,typ,unit,invert in keys:
  i=item('Redis host: '+name,key,typ,'host');i['units']=unit
  if invert:i['preprocessing']=[{'type':'JAVASCRIPT','parameters':['return 100 - Number(value);']}]
  prototypes.append(i)
 rules.append(dict(uuid=uid('lld/'+group),name='Redis host: optional '+group,type='ZABBIX_PASSIVE',key='agent.ping[rdm_'+group.lower()+']',delay='5m',lifetime='0',preprocessing=[{'type':'JAVASCRIPT','parameters':['if ("{$REDIS.HOST.ENABLED}" !== "1" || "{$REDIS.HOST.'+group+'.ENABLED}" !== "1") return "[]"; return JSON.stringify([{ "{#SCOPE}": "host", "{#CPU}": "all", "{#PAVAILABLE}": "pavailable", "{#AVAILABLE}": "available" }]);']}],item_prototypes=prototypes))
net=dict(uuid=uid('lld/network'),name='Redis host: optional network',type='ZABBIX_PASSIVE',key='rdm.net.discovery["{$REDIS.HOST.ENABLED}","{$REDIS.HOST.NETWORK.ENABLED}"]',delay='5m',lifetime='0',preprocessing=[{'type':'JAVASCRIPT','parameters':['if ("{$REDIS.HOST.ENABLED}" !== "1" || "{$REDIS.HOST.NETWORK.ENABLED}" !== "1") return "[]"; return value;']}],filter={'evaltype':'AND','conditions':[{'macro':'{#IFNAME}','value':'{$REDIS.HOST.IF.REGEX}','operator':'MATCHES_REGEX','formulaid':'A'}]},item_prototypes=[])
for direction in ['in','out']:
 for mode in ['bytes','errors','dropped']:
  i=item('Redis host: {#IFNAME} '+direction+' '+mode,f'net.if.{direction}["{{#IFNAME}}",{mode}]','FLOAT','host');i['preprocessing']=[{'type':'CHANGE_PER_SECOND','parameters':[]}];i['units']='Bps' if mode=='bytes' else ''
  net['item_prototypes'].append(i)
rules.append(net)
for r in rules[:3]:
 group=r['name'].split()[-1]
 first=r['item_prototypes'][0]['key']
 tp=trig('host/'+group,'Redis host: '+group+' usage high',expr(first,'min','5m')+'>{$REDIS.HOST.'+group+'.WARN}')
 r['trigger_prototypes']=[tp]
disk=dict(uuid=uid('lld/disk'),name='Redis host: optional disk IO',type='ZABBIX_PASSIVE',key='rdm.disk.discovery["{$REDIS.HOST.ENABLED}","{$REDIS.HOST.DISK.ENABLED}"]',delay='5m',lifetime='0',preprocessing=[{'type':'JAVASCRIPT','parameters':['if ("{$REDIS.HOST.ENABLED}" !== "1" || "{$REDIS.HOST.DISK.ENABLED}" !== "1") return "[]"; return value;']}],filter={'evaltype':'AND','conditions':[{'macro':'{#DEVNAME}','value':'{$REDIS.HOST.DEV.REGEX}','operator':'MATCHES_REGEX','formulaid':'A'}]},item_prototypes=[])
rawkey='vfs.file.contents[/sys/block/{#DEVNAME}/stat]'
i=item('Redis host: {#DEVNAME} raw disk statistics',rawkey,'TEXT','host');i.update(trends='0',history='1d');disk['item_prototypes'].append(i)
for op,offset in [('read',0),('write',4)]:
 for label,index in [('ops',offset),('time',offset+3)]:
  key='rdm.host.disk.'+op+'.'+label+'[{#DEVNAME}]'
  i=item('Redis host: {#DEVNAME} '+op+' '+label+' rate',key,'FLOAT','host')
  i.update(type='DEPENDENT',delay='0',master_item={'key':rawkey},preprocessing=[{'type':'JAVASCRIPT','parameters':['return Number(value.trim().split(/\\s+/)['+str(index)+']);']},{'type':'CHANGE_PER_SECOND','parameters':[]}])
  i['units']='ops/s' if label=='ops' else 'ms/s'
  disk['item_prototypes'].append(i)
 key='rdm.host.disk.'+op+'.await[{#DEVNAME}]'
 opskey='rdm.host.disk.'+op+'.ops[{#DEVNAME}]'
 timekey='rdm.host.disk.'+op+'.time[{#DEVNAME}]'
 i=item('Redis host: {#DEVNAME} '+op+' average latency',key,'FLOAT','host');i.update(type='CALCULATED',params='last(//'+timekey+')/(last(//'+opskey+')+(last(//'+opskey+')=0))',units='ms')
 disk['item_prototypes'].append(i)
disk['trigger_prototypes']=[trig('disk-latency','Redis host: {#DEVNAME} disk write latency high',expr('rdm.host.disk.write.await[{#DEVNAME}]','min','5m')+'>{$REDIS.HOST.DISK.LATENCY.WARN}')]
rules.append(disk)
# agent.ping has no arguments: dependent LLD uses the existing collector, emits singleton rows.
for r in rules[:3]:
 r['type']='DEPENDENT';r['key']='rdm.host.discovery.'+r['name'].split()[-1].lower();r['delay']='0';r['master_item']={'key':masterkey}
 # collector is polled every minute; JavaScript only emits the singleton and does no host work.
from enrich import enrich
enrich(globals())
template=dict(uuid=uid('template'),template=T,name=T,dashboards=dashboards,description='Passive Debian Docker Redis monitor v1.1.0. Requires rdm.collect UserParameter + Python collector. Host metrics default off. Set HOST.ENABLED=1 to create optional host items; switch individual groups off to avoid duplicate keys. See README.',groups=[{'name':'Templates/Redis Docker'}],items=items,discovery_rules=rules,macros=[{'macro':'{$REDIS.'+k+'}','value':v} for k,v in macros.items()])
for ver in sys.argv[1:] or ['6.2']:
 import copy
 t=copy.deepcopy(template)
 if ver!='6.2':
  for dashboard in t['dashboards']:
   for page in dashboard['pages']:
    for index,widget in enumerate(page['widgets']):
     widget['type']='graph';widget['x']=str(int(widget['x'])*3);widget['width']=str(int(widget['width'])*3)
     widget['fields']=[f for f in widget['fields'] if f['name']!='source_type']
     for field in widget['fields']:
      if field['name']=='graphid':field['name']='graphid.0'
     widget['fields'].append({'type':'STRING','name':'reference','value':'RDM'+chr(65+index//26)+chr(65+index%26)})
  for r in t['discovery_rules']:r.update(lifetime='7d',lifetime_type='DELETE_AFTER',enabled_lifetime_type='DISABLE_IMMEDIATELY')
 exp={'version':ver,'template_groups':[{'uuid':uid('group'),'name':'Templates/Redis Docker'}],'templates':[t],'triggers':triggers,'graphs':graphs}
 if ver=='6.2':exp['date']='2026-10-01T09:50:00Z'
 path=P/('template_redis_docker_passive_'+ver.replace('.','_')+'.yaml')
 path.write_text(yaml.safe_dump({'zabbix_export':exp},sort_keys=False,allow_unicode=False),encoding='utf8')
 print(path)
