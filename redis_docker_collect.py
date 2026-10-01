#!/usr/bin/python3
"""Read-only Redis/Docker collector; Python stdlib; no shell evaluation."""
import json, os, pathlib, re, subprocess, sys, time

CONFIG_DIR = pathlib.Path('/etc/zabbix/redis-docker')

def run(args, timeout=2, env=None):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode:
        raise RuntimeError('command failed: ' + pathlib.Path(args[0]).name)
    return p.stdout.strip()

def parse_info(raw):
    result = {}
    for line in raw.splitlines():
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, value = line.split(':', 1)
        try:
            result[key] = int(value)
        except ValueError:
            try:
                result[key] = float(value)
            except ValueError:
                result[key] = value
    return result

def validate(container, data_path, mount_path, port):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', container):
        raise ValueError('invalid container name')
    for path in [data_path, mount_path]:
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path) or '..' in pathlib.PurePosixPath(path).parts:
            raise ValueError('paths must be absolute without spaces or parent traversal')
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('invalid Redis container port')
    data, mount = os.path.realpath(data_path), os.path.realpath(mount_path)
    if mount == '/' or os.path.commonpath([data, mount]) != mount:
        raise ValueError('data path must be within a dedicated mount path')
    return data, mount

def cli_command(container, port, json_output=False):
    cfg_path = CONFIG_DIR / (container + '.json')
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    env = os.environ.copy()
    args = ['/usr/bin/docker', 'exec']
    if 'password' in cfg:
        env['REDISCLI_AUTH'] = cfg['password']
        args += ['--env', 'REDISCLI_AUTH']
    args += [container, 'redis-cli', '--json' if json_output else '--raw', '-h', '127.0.0.1', '-p', port]
    if cfg.get('username'):
        args += ['--user', cfg['username']]
    if cfg.get('tls'):
        args += ['--tls']
        for field, flag in [('cacert', '--cacert'), ('cert', '--cert'), ('key', '--key')]:
            if cfg.get(field):
                args += [flag, cfg[field]]
    return args, env

def collect(container, data_path, mount_path, port):
    d = {'collector_ok': 0, 'docker_ok': 0, 'container_running': 0, 'ping_ok': 0, 'error': ''}
    data, mount = validate(container, data_path, mount_path, port)
    d['mount_ok'] = int(os.path.ismount(mount))
    # Never substitute root filesystem statistics for an absent mount.
    if d['mount_ok']:
        fs = os.statvfs(mount)
        d['fs_readonly'] = int(bool(fs.f_flag & os.ST_RDONLY))
        d['fs_free'] = fs.f_bavail * fs.f_frsize
        denom = fs.f_blocks - fs.f_bfree + fs.f_bavail
        if denom > 0:
            d['fs_used_pct'] = 100 * (fs.f_blocks - fs.f_bfree) / denom
        if fs.f_files > 0:
            d['inode_used_pct'] = 100 * (fs.f_files - fs.f_ffree) / fs.f_files
    try:
        c = json.loads(run(['/usr/bin/docker', 'inspect', '--type', 'container', container]))[0]
        d['docker_ok'] = 1
    except Exception:
        # Missing container and inaccessible daemon are different failures.
        try:
            run(['/usr/bin/docker', 'version', '--format', '{{.Server.Version}}'])
            d['docker_ok'] = 1
            d['error'] = 'container missing'
        except Exception:
            d['error'] = 'Docker daemon inaccessible or inspect failed'
        return d
    d['container_running'] = int(bool(c['State']['Running']))
    d['container_restarts'] = c.get('RestartCount', 0)
    d['container_id'] = c['Id']
    d['container_health'] = c['State'].get('Health', {}).get('Status', 'none')
    mounts = c.get('Mounts', [])
    d['bind_ok'] = int(any(m.get('Type') == 'bind' and m.get('Destination') == '/data'
                           and os.path.realpath(m.get('Source', '')) == data and m.get('RW')
                           for m in mounts))
    if not d['container_running']:
        d['error'] = 'container not running'
        return d
    args, env = cli_command(container, port)
    start = time.monotonic()
    try:
        pong = run(args + ['PING'], env=env)
    except Exception:
        d['error'] = 'Redis PING command failed or timed out'
        return d
    d['redis_ms'] = (time.monotonic() - start) * 1000
    d['ping_ok'] = int(pong == 'PONG')
    if not d['ping_ok']:
        d['error'] = 'Redis PING failed (authentication, ACL, TLS or port)'
        return d
    try:
        info = parse_info(run(args + ['INFO'], timeout=3, env=env))
    except Exception:
        d['error'] = 'Redis INFO command failed or timed out'
        return d
    if 'redis_version' not in info:
        d['error'] = 'Redis INFO denied or invalid'
        return d
    d['info'] = info
    if info.get('maxmemory', 0) > 0:
        d['memory_used_pct'] = 100 * info['used_memory'] / info['maxmemory']
    if info.get('maxclients', 0) > 0:
        d['clients_used_pct'] = 100 * info['connected_clients'] / info['maxclients']
    hits, misses = info.get('keyspace_hits', 0), info.get('keyspace_misses', 0)
    if hits + misses:
        d['hit_ratio'] = 100 * hits / (hits + misses)
    # Check actual Redis persistence dir, not just Docker /data configuration.
    try:
        raw = run(args + ['CONFIG', 'GET', 'dir'], env=env).splitlines()
    except Exception:
        d['error'] = 'CONFIG GET dir command failed or timed out'
        return d
    if len(raw) != 2 or raw[0] != 'dir':
        d['error'] = 'CONFIG GET dir denied or invalid; permit config|get to monitoring ACL'
        return d
    d['redis_dir'] = raw[1]
    if raw[1].rstrip('/') != '/data':
        d['bind_ok'] = 0
    # Optional enrichment uses existing INFO and one bounded CONFIG query.
    d['databases'] = {}
    d['db_discovery'] = []
    for name, text in info.items():
        if re.fullmatch(r'db[0-9]+', name) and isinstance(text, str):
            stats = {}
            for part in text.split(','):
                k, _, v = part.partition('=')
                if k in ['keys', 'expires', 'avg_ttl'] and v.isdigit():
                    stats[k] = int(v)
            if 'keys' in stats:
                d['databases'][name] = stats
                d['db_discovery'].append({'{#DB}': name})
    d['replicas'] = {}
    d['replica_discovery'] = []
    for name, text in info.items():
        if re.fullmatch(r'slave[0-9]+', name) and isinstance(text, str):
            parts = dict(part.split('=', 1) for part in text.split(',') if '=' in part)
            if 'ip' in parts and 'port' in parts and parts.get('offset', '').isdigit():
                ident = parts['ip'] + ':' + parts['port']
                peer = {'ip': parts['ip'], 'port': parts['port'], 'state': parts.get('state', 'unknown'), 'offset': int(parts['offset'])}
                if 'master_repl_offset' in info:
                    peer['lag_bytes'] = max(0, info['master_repl_offset'] - peer['offset'])
                if parts.get('lag', '').isdigit():
                    peer['lag_seconds'] = int(parts['lag'])
                d['replicas'][ident] = peer
                d['replica_discovery'].append({'{#PEER}': ident})
    d['config_snapshot_ok'] = 0
    # Redis 7+ supports an explicit list, so no password-bearing CONFIG GET *.
    if int(str(info['redis_version']).split('.')[0]) >= 7:
        selected = ['maxmemory', 'maxmemory-policy', 'maxclients', 'appendonly', 'appendfsync', 'save', 'dir', 'dbfilename', 'appenddirname', 'slowlog-log-slower-than', 'slowlog-max-len']
        try:
            json_args, env = cli_command(container, port, json_output=True)
            config = json.loads(run(json_args + ['CONFIG', 'GET'] + selected, timeout=2, env=env))
            if isinstance(config, list) and len(config) % 2 == 0:
                config = dict(zip(config[::2], config[1::2]))
            if not isinstance(config, dict) or 'dir' not in config:
                raise ValueError('invalid config reply')
            config = {k: str(v) for k, v in config.items() if k in selected}
            d['config_snapshot'] = json.dumps(config, sort_keys=True, separators=(',', ':'))
            d['config_snapshot_ok'] = 1
        except Exception:
            d['config_error'] = 'Selected CONFIG GET query failed; base monitoring remains available'
    else:
        d['config_error'] = 'Config snapshot requires Redis 7+ and redis-cli JSON support'
    d['collector_ok'] = 1
    return d

def slowlog_collect(container, port, enabled):
    validate(container, '/mnt/data', '/mnt', port)
    if enabled not in ['0', '1']:
        raise ValueError('invalid slowlog flag')
    if enabled == '0':
        return {'enabled': 0, 'ok': 1}
    d = {'enabled': 1, 'ok': 0}
    try:
        args, env = cli_command(container, port, json_output=True)
        length = json.loads(run(args + ['SLOWLOG', 'LEN'], env=env))
        rows = json.loads(run(args + ['SLOWLOG', 'GET', '1'], env=env))
        if not isinstance(length, int) or length < 0 or not isinstance(rows, list):
            raise ValueError('invalid slowlog reply')
        d['length'] = length
        if rows:
            row = rows[0]
            # Do not export commands, command arguments or client identifiers.
            d['last_id'] = int(row[0])
            d['last_timestamp'] = int(row[1])
            d['last_duration_usec'] = int(row[2])
        d['ok'] = 1
    except Exception:
        d['error'] = 'SLOWLOG query failed; check container, ACL, port and TLS'
    return d

def discover(kind, enabled, group_enabled):
    if kind not in ['network', 'disk'] or enabled not in ['0', '1'] or group_enabled not in ['0', '1']:
        raise ValueError('invalid discovery parameters')
    if enabled != '1' or group_enabled != '1':
        return []
    directory, macro = ('/sys/class/net', '{#IFNAME}') if kind == 'network' else ('/sys/block', '{#DEVNAME}')
    return [{macro: p.name} for p in sorted(pathlib.Path(directory).iterdir())]

if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--slowlog':
        try:
            result = slowlog_collect(*sys.argv[2:])
        except Exception:
            result = {'enabled': 1, 'ok': 0, 'error': 'Invalid slowlog arguments or configuration'}
    elif len(sys.argv) == 5 and sys.argv[1] == '--discover':
        try:
            result = discover(*sys.argv[2:])
        except Exception:
            # A failed enabled discovery must be unsupported, not an empty healthy result.
            print('ZBX_NOTSUPPORTED: discovery failed')
            sys.exit(1)
    else:
        try:
            if len(sys.argv) != 5:
                raise ValueError('expected: container data_path mount_path container_port')
            result = collect(*sys.argv[1:])
        except Exception as e:
            # Never output command stderr or credentials.
            result = {'collector_ok': 0, 'error': type(e).__name__ + ': collection failed; check configuration and access'}
    print(json.dumps(result, separators=(',', ':'), allow_nan=False))
