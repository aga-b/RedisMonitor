# 1.1.0 - 2026-10-01

- V1.0 passive model, template/item key ve UUID'leri korundu.
- INFO'dan Redis CPU rate, trafik rate, ayrintili bellek ve persistence metrikleri.
- DB bazinda keys/expires/avg_ttl discovery ve graph prototype.
- Macro ile kapatilabilen ayri passive slowlog collector; buffer boyu yerine ID rate.
- Secilmis operasyonel config snapshot; config/surum/role degisim alarmlari.
- Uptime reset, fragmentation, slowlog ve temel replication alarmlari.
- Opsiyonel replica discovery, gercek offset farkindan byte lag.
- Docker/disk alarmlarina bagimlilik ve stale Redis degerlerine collector kontrolu.
- PING sure adi docker exec/CLI maliyetini aciklayacak sekilde duzeltildi.
- 16 grafik, bir dashboard ve DB/replica grafik prototipleri.
- 29 yerel kontrol; eski key/UUID korunmasi ve 32 karakter UUID dahil.
- 6.2, 7.0 ve 7.4 export; 7.x dashboard field/grid farklari uyarlandi.

# 1.0.0 - 2026-10-01

- Zabbix 6.2, 7.0 ve 7.4 icin passive Debian Docker Redis template'leri.
- Tek Redis/Docker collector ve dependent item'lar.
- Host macro'lariyla data path, mount, container ve Redis portu.
- Varsayilan kapali, grup bazinda host CPU/RAM/swap/network/disk izlemesi.
- Docker, Redis persistence ve filesystem alarmlari; kurulum rehberi.
