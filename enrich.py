"""Add Redis observability while retaining all v1 item keys and UUIDs."""
import json

def enrich(ns):
 item,uid,tags,trig,expr=(ns[k] for k in ['item','uid','tags','trig','expr'])
 items,rules,triggers,macros=(ns[k] for k in ['items','rules','triggers','macros'])
 masterkey,T=ns['masterkey'],ns['T']
 graphs=[]
 def dep(field,name,typ='UNSIGNED',unit='',key=None,master=None,extra=None,component='redis'):
  key=key or 'rdm.'+field
  i=item('Redis Docker: '+name,key,typ,component)
  i.update(type='DEPENDENT',delay='0',master_item={'key':master or masterkey},preprocessing=[{'type':'JSONPATH','parameters':['$.'+field],'error_handler':'DISCARD_VALUE'}]+(extra or []))
  if unit:i['units']=unit
  if typ in ['TEXT','CHAR']:i['trends']='0'
  items.append(i)
  return i
 macros.update({'SLOWLOG.ENABLED':'1','SLOWLOG.RATE.WARN':'1','DB.MATCHES':'^db[0-9]+$','DB.NOT.MATCHES':'^$','REPLICATION.ENABLED':'0','REPLICATION.LAG.WARN':'30','FRAG.RATIO.WARN':'1.5','FRAG.BYTES.MIN':'33554432','FRAG.MEMORY.MIN':'104857600','PING.EXEC.WARN':'500','CONFIG.CHANGE.ALERT':'1'})
 next(i for i in items if i['key']=='rdm.info.latest_fork_usec')['units']='us'
 next(i for i in items if i['key']=='rdm.info.rdb_last_save_time')['units']='unixtime'
 next(i for i in items if i['key']=='rdm.info.uptime_in_seconds')['units']='s'
 # Keep redis_ms key; explicitly name the measured operation.
 next(i for i in items if i['key']=='rdm.redis_ms')['name']='Redis Docker: PING including docker exec and redis-cli startup'
 units_bytes='used_memory_peak used_memory_dataset used_memory_overhead used_memory_startup mem_fragmentation_bytes allocator_allocated allocator_active allocator_resident allocator_frag_bytes allocator_rss_bytes rss_overhead_bytes mem_clients_normal mem_clients_slaves mem_replication_backlog mem_aof_buffer mem_not_counted_for_evict used_memory_scripts used_memory_lua aof_buffer_length rdb_last_cow_size aof_last_cow_size total_net_input_bytes total_net_output_bytes client_recent_max_input_buffer client_recent_max_output_buffer'.split()
 for f in units_bytes:dep('info.'+f,f.replace('_',' '),'FLOAT' if f in ['mem_fragmentation_bytes','allocator_frag_bytes','allocator_rss_bytes','rss_overhead_bytes'] else 'UNSIGNED','B')
 for f in 'allocator_frag_ratio allocator_rss_ratio rss_overhead_ratio instantaneous_input_kbps instantaneous_output_kbps used_cpu_sys used_cpu_user used_cpu_sys_children used_cpu_user_children'.split():
  dep('info.'+f,f.replace('_',' '),'FLOAT','s' if f.startswith('used_cpu') else '')
 for f in 'aof_last_rewrite_time_sec aof_current_rewrite_time_sec rdb_last_bgsave_time_sec rdb_current_bgsave_time_sec'.split():dep('info.'+f,f.replace('_',' '),'FLOAT','s') # Redis uses -1 before first operation.
 for f in 'aof_rewrite_scheduled aof_pending_rewrite aof_pending_bio_fsync rdb_bgsave_in_progress active_defrag_running lazyfree_pending_objects process_id tcp_port cluster_enabled pubsub_channels pubsub_patterns sync_full sync_partial_ok sync_partial_err connected_slaves master_repl_offset slave_repl_offset master_last_io_seconds_ago master_sync_in_progress repl_backlog_active repl_backlog_size repl_backlog_histlen'.split():
  dep('info.'+f,f.replace('_',' '),'FLOAT' if f=='master_last_io_seconds_ago' else 'UNSIGNED','s' if f=='master_last_io_seconds_ago' else '')
 for f in 'maxmemory_policy redis_mode master_host master_link_status'.split():dep('info.'+f,f.replace('_',' '),'CHAR')
 dep('config_snapshot','Selected operational config snapshot','TEXT',component='config',extra=[{'type':'DISCARD_UNCHANGED_HEARTBEAT','parameters':['1h']}])
 dep('config_snapshot_ok','Selected config query successful',component='config')
 # Rates reset naturally via CHANGE_PER_SECOND; counters remain untouched.
 for f in ['evicted_keys','expired_keys','keyspace_hits','keyspace_misses','rejected_connections','total_commands_processed','total_connections_received','total_net_input_bytes','total_net_output_bytes']:
  dep('info.'+f,f.replace('_',' ')+' per second','FLOAT','Bps' if f.startswith('total_net_') else '1/s',key='rdm.rate.'+f,extra=[{'type':'CHANGE_PER_SECOND','parameters':[]}])
 for scope in ['sys','user','sys_children','user_children']:
  dep('info.used_cpu_'+scope,'Redis CPU '+scope+' (one core = 100%)','FLOAT','%',key='rdm.cpu.'+scope+'.pct',extra=[{'type':'CHANGE_PER_SECOND','parameters':[]},{'type':'MULTIPLIER','parameters':['100']}])
 i=item('Redis Docker: cache hit ratio during polling interval','rdm.hit_ratio.interval','FLOAT');i.update(type='CALCULATED',units='%',params='100*last(//rdm.rate.keyspace_hits)/(last(//rdm.rate.keyspace_hits)+last(//rdm.rate.keyspace_misses)+(last(//rdm.rate.keyspace_hits)+last(//rdm.rate.keyspace_misses)=0))');items.append(i)
 # Empty healthy databases are absent in INFO, not fabricated as db0.
 db=dict(uuid=uid('lld/db'),name='Redis Docker: database discovery',type='DEPENDENT',key='rdm.db.discovery',delay='0',lifetime='7d',master_item={'key':masterkey},preprocessing=[{'type':'JAVASCRIPT','parameters':['var d=JSON.parse(value); if(d.collector_ok!==1 || !d.db_discovery) throw "Collector data unavailable"; return JSON.stringify(d.db_discovery);']}],filter={'evaltype':'AND','conditions':[{'macro':'{#DB}','value':'{$REDIS.DB.MATCHES}','operator':'MATCHES_REGEX','formulaid':'A'},{'macro':'{#DB}','value':'{$REDIS.DB.NOT.MATCHES}','operator':'NOT_MATCHES_REGEX','formulaid':'B'}]},item_prototypes=[],graph_prototypes=[])
 for f,unit in [('keys',''),('expires',''),('avg_ttl','ms')]:
  i=item('Redis Docker: {#DB} '+f,'rdm.db.'+f+'[{#DB}]');i.update(type='DEPENDENT',delay='0',master_item={'key':masterkey},preprocessing=[{'type':'JSONPATH','parameters':['$.databases.{#DB}.'+f],'error_handler':'DISCARD_VALUE'}],units=unit);db['item_prototypes'].append(i)
 def graph(name,keys,prototype=False):
  g={'uuid':uid('graph/'+name),'name':name,'graph_items':[{'sortorder':str(n),'color':['199C0D','F63100','2774A4','A54F10','C7A72D'][n%5],'item':{'host':T,'key':key}} for n,key in enumerate(keys)]}
  return g
 db['graph_prototypes'].append(graph('Redis Docker: {#DB} keys and expiring keys',['rdm.db.keys[{#DB}]','rdm.db.expires[{#DB}]']))
 rules.append(db)
 repl=dict(uuid=uid('lld/replicas'),name='Redis Docker: connected replica discovery',type='DEPENDENT',key='rdm.replica.discovery',delay='0',lifetime='7d',master_item={'key':masterkey},preprocessing=[{'type':'JAVASCRIPT','parameters':['if("{$REDIS.REPLICATION.ENABLED}"!=="1") return "[]"; var d=JSON.parse(value); if(d.collector_ok!==1 || !d.replica_discovery) throw "Collector data unavailable"; return JSON.stringify(d.replica_discovery);']}],item_prototypes=[],trigger_prototypes=[],graph_prototypes=[])
 for f,typ,unit in [('lag_bytes','UNSIGNED','B'),('lag_seconds','UNSIGNED','s'),('offset','UNSIGNED','B'),('state','CHAR','')]:
  i=item('Redis Docker: replica {#PEER} '+f,'rdm.replica.'+f+'["{#PEER}"]',typ)
  i.update(type='DEPENDENT',delay='0',master_item={'key':masterkey},preprocessing=[{'type':'JSONPATH','parameters':['$.replicas["{#PEER}"].'+f],'error_handler':'DISCARD_VALUE'}],units=unit)
  if typ=='CHAR':i['trends']='0'
  repl['item_prototypes'].append(i)
 repl['trigger_prototypes'].append(trig('replica/lag','Redis Docker: replica {#PEER} acknowledgement lag high',expr('rdm.replica.lag_seconds["{#PEER}"]','min','5m')+'>{$REDIS.REPLICATION.LAG.WARN} and {$REDIS.REPLICATION.ENABLED}=1 and '+expr('rdm.collector_ok')+'=1'))
 repl['graph_prototypes'].append(graph('Redis Docker: replica {#PEER} byte lag',['rdm.replica.lag_bytes["{#PEER}"]']))
 rules.append(repl)
 slowkey='rdm.slowlog["{$REDIS.CONTAINER}","{$REDIS.PORT}","{$REDIS.SLOWLOG.ENABLED}"]'
 i=item('Redis Docker: slowlog collector JSON',slowkey,'TEXT','slowlog');i.update(trends='0',history='1d');items.append(i)
 for f,unit in [('enabled',''),('ok',''),('length',''),('last_id',''),('last_timestamp','unixtime'),('last_duration_usec','us')]:dep(f,'Slowlog '+f,'UNSIGNED',unit,key='rdm.slowlog.'+f,master=slowkey,component='slowlog')
 dep('last_id','New slowlog entries per second','FLOAT','1/s',key='rdm.slowlog.rate',master=slowkey,extra=[{'type':'CHANGE_PER_SECOND','parameters':[]}],component='slowlog')
 healthy=expr('rdm.collector_ok')+'=1'
 for ident,name,expression,sev in [
  ('fragmentation','memory fragmentation high',expr('rdm.info.mem_fragmentation_ratio','min','15m')+'>{$REDIS.FRAG.RATIO.WARN} and '+expr('rdm.info.mem_fragmentation_bytes','min','15m')+'>{$REDIS.FRAG.BYTES.MIN} and '+expr('rdm.info.used_memory')+'>{$REDIS.FRAG.MEMORY.MIN}','WARNING'),
  ('config-read-failed','selected operational config query failed','{$REDIS.CONFIG.CHANGE.ALERT}=1 and '+expr('rdm.config_snapshot_ok','max','3m')+'=0','WARNING'),
  ('config-change','operational config changed','{$REDIS.CONFIG.CHANGE.ALERT}=1 and '+expr('rdm.config_snapshot','change')+'=1 and '+expr('rdm.config_snapshot_ok')+'=1','INFO'),
  ('version-change','Redis version changed',expr('rdm.info.redis_version','change')+'=1','INFO'),
  ('role-change','Redis role changed',expr('rdm.info.role','change')+'=1','WARNING'),
  ('redis-restart','Redis uptime reset',expr('rdm.info.uptime_in_seconds','change')+'<0','INFO'),
  ('ping-exec-slow','PING including docker exec is slow',expr('rdm.redis_ms','min','5m')+'>{$REDIS.PING.EXEC.WARN}','WARNING'),
  ('slowlog-failed','slowlog query failed','{$REDIS.SLOWLOG.ENABLED}=1 and '+expr('rdm.slowlog.ok','max','3m')+'=0','WARNING'),
  ('slowlog-no-data','slowlog collector data missing','{$REDIS.SLOWLOG.ENABLED}=1 and '+expr(slowkey,'nodata','5m')+'=1','WARNING'),
  ('slowlog-rate','many new slowlog entries','{$REDIS.SLOWLOG.ENABLED}=1 and '+expr('rdm.slowlog.rate','min','5m')+'>{$REDIS.SLOWLOG.RATE.WARN}','WARNING'),
  ('masterlink','replication master link down','{$REDIS.REPLICATION.ENABLED}=1 and '+expr('rdm.info.role')+'="slave" and '+expr('rdm.info.master_link_status')+'="down"','HIGH'),
  ('masterio','no recent interaction with master','{$REDIS.REPLICATION.ENABLED}=1 and '+expr('rdm.info.role')+'="slave" and '+expr('rdm.info.master_last_io_seconds_ago','min','5m')+'>{$REDIS.REPLICATION.LAG.WARN}','WARNING')]:
  triggers.append(trig(ident,'Redis Docker: '+name,expression+' and '+healthy,sev))
 # Suppress stale Redis values after failed collection.
 rediskeys=['rdm.info.','rdm.memory_used_pct','rdm.clients_used_pct']
 for t in triggers:
  if any(k in t['expression'] for k in rediskeys) and healthy not in t['expression']:t['expression']+=' and '+healthy
 byid={t['uuid']:t for t in triggers}
 def dependency(triggerid,causeids):
  t=byid[uid('trigger/'+triggerid)]
  t['dependencies']=[{'name':byid[uid('trigger/'+cause)]['name'],'expression':byid[uid('trigger/'+cause)]['expression']} for cause in causeids]
 for t in triggers:
  if t['uuid']!=uid('trigger/nodata'):t['dependencies']=[{'name':byid[uid('trigger/nodata')]['name'],'expression':byid[uid('trigger/nodata')]['expression']}]
 dependency('container_running',['nodata','docker_ok'])
 dependency('ping_ok',['nodata','docker_ok','container_running'])
 dependency('collector_ok',['nodata','docker_ok','container_running','ping_ok'])
 dependency('bind_ok',['nodata','container_running','mount_ok'])
 dependency('health',['nodata','container_running'])
 for id in ['slowlog-failed','slowlog-rate','slowlog-no-data']:dependency(id,['nodata','docker_ok','container_running','ping_ok'])
 for f in ['fs_used_pct','inode_used_pct']:dependency(f+'warn',['nodata','mount_ok',f+'crit']);dependency(f+'crit',['nodata','mount_ok'])
 for name,keys in [
  ('Availability and exec PING',['rdm.redis_ms','rdm.ping_ok']),
  ('Clients',['rdm.info.connected_clients','rdm.info.blocked_clients','rdm.info.maxclients']),
  ('Operations',['rdm.info.instantaneous_ops_per_sec','rdm.rate.total_commands_processed']),
  ('Redis CPU',['rdm.cpu.user.pct','rdm.cpu.sys.pct','rdm.cpu.user_children.pct','rdm.cpu.sys_children.pct']),
  ('Redis traffic',['rdm.rate.total_net_input_bytes','rdm.rate.total_net_output_bytes']),
  ('Redis memory',['rdm.info.used_memory','rdm.info.used_memory_rss','rdm.info.used_memory_peak','rdm.info.used_memory_dataset','rdm.info.maxmemory']),
  ('Memory overhead',['rdm.info.used_memory_overhead','rdm.info.mem_clients_normal','rdm.info.mem_aof_buffer']),
  ('Fragmentation',['rdm.info.mem_fragmentation_ratio','rdm.info.allocator_frag_ratio','rdm.info.rss_overhead_ratio']),
  ('Keyspace activity',['rdm.rate.keyspace_hits','rdm.rate.keyspace_misses','rdm.rate.expired_keys','rdm.rate.evicted_keys']),
  ('Cache hit ratio',['rdm.hit_ratio','rdm.hit_ratio.interval']),
  ('AOF size',['rdm.info.aof_current_size','rdm.info.aof_base_size']),
  ('Persistence duration',['rdm.info.rdb_last_bgsave_time_sec','rdm.info.aof_last_rewrite_time_sec']),
  ('Persistence CoW memory',['rdm.info.rdb_last_cow_size','rdm.info.aof_last_cow_size']),
  ('Slowlog',['rdm.slowlog.rate','rdm.slowlog.length']),
  ('Data disk usage',['rdm.fs_used_pct','rdm.inode_used_pct']),
  ('Docker restarts',['rdm.container_restarts'])]:graphs.append(graph('Redis Docker: '+name,keys))
 dashboard={'uuid':uid('dashboard/overview'),'name':'Redis Docker overview','pages':[{'name':'Overview','widgets':[]}]}
 for n,g in enumerate(graphs):
  dashboard['pages'][0]['widgets'].append({'type':'GRAPH_CLASSIC','name':g['name'],'x':str((n%2)*12),'y':str((n//2)*5),'width':'12','height':'5','fields':[{'type':'INTEGER','name':'source_type','value':'0'},{'type':'GRAPH','name':'graphid','value':{'host':T,'name':g['name']}}]})
 ns['graphs']=graphs;ns['dashboards']=[dashboard]
