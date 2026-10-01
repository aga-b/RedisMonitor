# RedisMonitor v1.1.0

Debian Docker Redis icin Zabbix 6.2, 7.0 ve 7.4 passive izleme.

V1.0'daki collector, Docker/disk kontrolleri, veri yolu makrolari ve eski
item key/UUID'leri korunur. Redis CPU/traffic rate, detayli bellek ve
persistence metrikleri, DB discovery, slowlog, config/surum/role degisim
alarmlari, temel replication ve dashboard eklendi.

## Guncelleme

Once collector ve redis_docker.conf dosyasini guncelleyin; ardindan Zabbix
surumune uygun YAML'i import edin. Host container/path ve host izleme
macro'lari korunur. Ayrintili adimlar UPGRADE.md dosyasindadir.

Slowlog icin +slowlog|len ve +slowlog|get ACL izinleri gerekir. Istemiyorsaniz
{$REDIS.SLOWLOG.ENABLED}=0 yapin. Host metrikleri varsayilan kapali; replication
alarmlari ve replica discovery varsayilan kapalidir.

## Dogrulama

29 yerel test gecti. UUID formati, v1 item key/UUID korumasi, collector
fixture'lari, graph/dashboard referanslari ve trigger bagimliliklari kontrol
edildi. Canli Docker/Zabbix import veya passive baglanti testi yapilmadi.
