# Debian uzerinde Docker Redis - Zabbix passive izleme

Surum: 1.1.0. Hedef Zabbix sunucu surumleri: 6.2 (6.2.6 dahil), 7.0 ve 7.4.
Agent host uzerinde calisir; Redis container icindedir. Python 3 ve hostta
Docker CLI gerekir. Agent veya Agent 2 kullanilabilir. Aktif agent, sender,
cron veya Zabbix Agent 2 Redis/Docker plugin gerektirmez.

Mevcut kurulumdan gecis icin once `UPGRADE.md` dosyasini okuyun.

## Dosyalar

- `template_redis_docker_passive_6_2.yaml`
- `template_redis_docker_passive_7_0.yaml`
- `template_redis_docker_passive_7_4.yaml`
- `redis_docker_collect.py`: hostta calisan salt okunur collector.
- `redis_docker.conf`: UserParameter tanimi.
- `redis-auth.example.json`: istege bagli ACL/parola ayari.
- `test_monitor.py`: fixture ve YAML/JavaScript kontrolleri.
- `build.py` ve `enrich.py`: YAML dosyalarinin tekrar uretimi (yalniz gelistirme icin PyYAML gerekir).

Ayni hosta bu uc YAML'den sadece sunucu surumune uygun olanini baglayin.
Template adi ve UUID'ler ortaktir; farkli versiyonlar alternatiflerdir.
Her Debian hostu icin ayri macro degerleri tanimlanabilir. V1.1 her hostta bir
Redis container izler. Temel replication metrikleri ve master tarafinda replica discovery vardir;
Redis Cluster/Sentinel topolojisi ve coklu container kesfi kapsam disindadir.

## Nasil calisir?

Zabbix server/proxy host agent'ina TCP 10050 uzerinden passive sorgu yollar.
Dakikada bir `rdm.collect[...]` JSON toplar. Redis, Docker ve filesystem
item'lari bu JSON'dan dependent olarak turetilir; her metrik icin tekrar
Docker exec veya Redis INFO calistirilmaz.

Collector Docker inspect ile daemon/container durumu, healthcheck, restart
sayisi ve /data bind mount'unu inceler. Container icinden redis-cli kullanarak
127.0.0.1 ve macroda verilen container portuna PING, INFO ve CONFIG GET dir
sorgular. Redis 7+ icin ek bir CONFIG GET sorgusu secilmis operasyonel
ayarlari takip eder; parola ve masterauth gibi ayarlar sorgulanmaz. CONFIG GET dir /data donmelidir. Varsayim: host bind mount'u
container /data dizinine bagli, Redis de /data icine yaziyor.

Port macro'su hosta yayinlanan port degil, Redis'in container icindeki portudur.
6379'u Zabbix icin publish etmeniz gerekmez. SSH 22 veya Docker TCP API 2375
bu template tarafindan kullanilmaz. Aktif agent olmadigi icin hostun Zabbix'e
10051 baglantisi gerekli degildir. Server/proxy'nin agent'a 10050 erisimi gerekir.
PING Redis portu/uygulama kontrolunu birlikte yapar; uygulama sunucusundan
Redis'e giden ag yolunun kontrolu gerekiyorsa o kaynaktan ek kontrol gerekir.

Collector SET, SAVE, BGSAVE, BGREWRITEAOF veya CONFIG SET yapmaz.
Persistence status degerlerini izler; diske yazilan verinin geri yuklenebilirligini
tek basina kanitlamaz. Restore testi ve backup ayrica yapilmalidir.

## Host makrolari

| Macro | Varsayilan | Aciklama |
|---|---|---|
| `{$REDIS.CONTAINER}` | `redis` | Docker container adi; Compose service adi ile ayni olmak zorunda degil |
| `{$REDIS.DATA.PATH}` | `/mnt/web-redis/data` | Hostta container /data'ya bind edilen dizin |
| `{$REDIS.MOUNT.PATH}` | `/mnt/web-redis` | Gercek ayri disk mount noktasi; / olamaz |
| `{$REDIS.PORT}` | `6379` | Container icindeki Redis portu; TLS varsa TLS portu |
| `{$REDIS.HOST.ENABLED}` | `0` | Tum istege bagli sunucu metriklerinin ana anahtari |
| `{$REDIS.HOST.CPU.ENABLED}` | `1` | Ana anahtar acikken CPU utilization ve load |
| `{$REDIS.HOST.MEMORY.ENABLED}` | `1` | Ana anahtar acikken RAM ve available memory |
| `{$REDIS.HOST.SWAP.ENABLED}` | `1` | Ana anahtar acikken swap yuzdesi |
| `{$REDIS.HOST.NETWORK.ENABLED}` | `0` | Ana anahtar acikken interface byte/error/drop hizlari |
| `{$REDIS.HOST.IF.REGEX}` | `^(eth[0-9]+\|en[a-zA-Z0-9]+)$` | Izlenecek interface adlari; ornek `^ens18$` |
| `{$REDIS.HOST.DISK.ENABLED}` | `0` | Ana anahtar acikken block device IOPS ve latency |
| `{$REDIS.HOST.DEV.REGEX}` | `^(sd[a-z]+\|vd[a-z]+\|nvme[0-9]+n[0-9]+)$` | Ornek: sadece veri diski icin `^sdb$` |
| `{$REDIS.AOF.REQUIRED}` | `1` | AOF kapaliysa alarm; yalniz RDB kullaniyorsan 0 |
| `{$REDIS.EVICTION.ALERT}` | `0` | Eviction cache politikasinda normal olabilir; kayip istenmiyorsa 1 |
| `{$REDIS.MEMORY.WARN}` | `80` | Redis maxmemory yuzdesi, 5 dakika |
| `{$REDIS.CLIENTS.WARN}` | `80` | Redis maxclients yuzdesi, 5 dakika |
| `{$REDIS.DISK.WARN}` | `75` | Veri filesystem/inode warning yuzdesi, 5 dakika |
| `{$REDIS.DISK.CRIT}` | `90` | Veri filesystem/inode critical yuzdesi, 5 dakika |
| `{$REDIS.HOST.CPU.WARN}` | `90` | CPU utilization warning yuzdesi, 5 dakika |
| `{$REDIS.HOST.MEMORY.WARN}` | `90` | RAM warning yuzdesi, 5 dakika |
| `{$REDIS.HOST.SWAP.WARN}` | `20` | Swap warning yuzdesi, 5 dakika |
| `{$REDIS.HOST.DISK.LATENCY.WARN}` | `50` | Disk write latency warning, ms, 5 dakika |

ENABLED/REQUIRED/ALERT anahtarlari sadece 0 veya 1 olmalidir. Container adi
ve path macro'larinda bosluk veya shell karakteri kullanmayin. Path'ler
absolute olmali; DATA.PATH MOUNT.PATH icinde bulunmalidir. /data hedefi bu
surumde sabittir. Named volume yerine bind mount beklenir.

Veri diski dogrudan `/mnt/web-redis/data` noktasina mount edilmisse iki path
macro'sunu da `/mnt/web-redis/data` yapabilirsiniz. Mount noktasi /mnt ise
MOUNT.PATH=/mnt ve DATA.PATH=/mnt/web-redis/data gibi ayarlayin.

## Yeni Redis makrolari

| Macro | Varsayilan | Aciklama |
|---|---|---|
| `{$REDIS.SLOWLOG.ENABLED}` | `1` | Ayri passive slowlog sorgusu; 0 iken Redis/Docker sorgusu yapmaz |
| `{$REDIS.SLOWLOG.RATE.WARN}` | `1` | Yeni slowlog kaydi/saniye; 5 dakika boyunca esik ustu |
| `{$REDIS.DB.MATCHES}` | `^db[0-9]+$` | Kesfedilecek DB adlari |
| `{$REDIS.DB.NOT.MATCHES}` | `^$` | Kesiften haric tutulacak DB adlari |
| `{$REDIS.REPLICATION.ENABLED}` | `0` | Replica discovery ve replication alarmlari |
| `{$REDIS.REPLICATION.LAG.WARN}` | `30` | Replica acknowledgement/master son iletisim esigi, saniye |
| `{$REDIS.FRAG.RATIO.WARN}` | `1.5` | Fragmentation ratio esigi |
| `{$REDIS.FRAG.BYTES.MIN}` | `33554432` | Alarm icin fragmentation byte en az 32 MiB |
| `{$REDIS.FRAG.MEMORY.MIN}` | `104857600` | Alarm icin Redis used_memory en az 100 MiB |
| `{$REDIS.PING.EXEC.WARN}` | `500` | Docker exec + redis-cli + PING toplam sure esigi, ms |
| `{$REDIS.CONFIG.CHANGE.ALERT}` | `1` | Secilmis operasyonel config degisimi ve config query hata alarmi |

Fragmentation alarmi ratio ve byte esiklerinin 15 dakika boyunca asildiginda
ve Redis'in used_memory degeri minimumdan buyuk oldugunda gelir. Kucuk veri
kumesinde salt RSS/used_memory orani gereksiz alarm uretmez.

## Tekrar CPU/RAM toplamasini engelleme

Hostta zaten Linux template'i varsa HOST.ENABLED=0 birakin. CPU/RAM/swap
item'lari olusturulmaz; onlar icin ikinci passive sorgu yapilmaz. Container,
Redis ve veri diski saglik kontrolleri calismaya devam eder.

Sadece CPU zaten izleniyorsa:

```text
{$REDIS.HOST.ENABLED}        = 1
{$REDIS.HOST.CPU.ENABLED}    = 0
{$REDIS.HOST.MEMORY.ENABLED} = 1
{$REDIS.HOST.SWAP.ENABLED}   = 1
```

Bu secim yalniz trigger'i susturmaz: CPU item'larini kesiften cikarir.
Mevcut item'lari otomatik arayip eslestirmez; macro'yu siz belirlemelisiniz.
Ayni key'e sahip item zaten varsa kesif hata verir: o grubu kapatin.

6.2'de kapatilan grubun kesfedilmis item'lari sonraki basarili LLD isleminde
silinir; ilgili gecmis veri de silinir. Yeni hostta varsayilan kapali oldugundan
bu item'lar hic olusmaz. 7.0/7.4'te sonraki basarili LLD'de hemen disable
olur, 7 gun sonra silinir. Degisiklik server config cache'e ve kesfe ulasinca
uygulanir; anlik degildir. CPU/RAM/swap LLD collector'dan dakikada bir
beslenir. Network/disk discovery 5 dakikada bir calisir.

Ana anahtar kapaliyken CPU/RAM/swap metrikleri toplanmaz. Network/disk icin
template'e ozel discovery komutu 5 dakikada bir sorgulanir, fakat kapali grupta
sysfs okumadan [] doner. Discovery key'leri rdm.net.discovery ve rdm.disk.discovery
oldugundan standart Linux template'inin kesif key'leriyle cakisma olmaz.
Aktif hale getirdiginiz gruplarin gercek metrik key'lerini baska template de
kullaniyorsa ilgili grubu macro'dan kapatin.

## Kurulum: Agent 2 ornegi

Bu komutlari hedef Debian hostunda paket dizininden root olarak calistirin.
Mevcut Redis'e veya Compose dosyasina degisiklik yapmaz.

```bash
install -d -m 0755 /usr/local/lib/zabbix
install -m 0755 redis_docker_collect.py /usr/local/lib/zabbix/redis_docker_collect.py
install -d -m 0755 /etc/zabbix/zabbix_agent2.d
install -m 0644 redis_docker.conf /etc/zabbix/zabbix_agent2.d/redis_docker.conf
install -d -o root -g zabbix -m 0750 /etc/zabbix/redis-docker
```

`/etc/zabbix/zabbix_agent2.conf` dosyasinda asagidaki ayarlari mevcut
sunucu/proxy IP adresine gore duzenleyin. Varsa ayni satiri guncelleyin,
tekrar eklemeyin. Include yolu dagitiminizdaki gercek yol olmali.

```ini
Server=ZABBIX_SERVER_VEYA_PROXY_IP
ListenPort=10050
Timeout=15
UnsafeUserParameters=0
Include=/etc/zabbix/zabbix_agent2.d/*.conf
```

ServerActive/Hostname ayarlari bu template'in passive sorgulari icin zorunlu
degildir. Mevcut diger aktif kontroller icin kullaniyorsaniz onlari koruyun.
6.2'de server/proxy Timeout degerinin de collector surelerine uygun olmasi
gerekir; ornek 20 saniye. 7.x'te passive agent/UserParameter item timeout
ayarini en az 15 saniye yapin. Varsayilan 3 saniye yetmeyebilir.

Docker rootful kurulumu ve `/usr/bin/docker` beklenir. Agent kullanicisina
Docker socket erisimi gerekir. Basit yontem:

```bash
usermod -aG docker zabbix
systemctl restart zabbix-agent2
```

Docker grubuna uyelik hostta root seviyesinde yetki saglar. Collector salt
okunur komutlar kullansa da bu uyeligin yetkisi daha genistir; bu modeli
kabul etmeyen ortamlarda kisitli bir aracilik servisi tasarlanmalidir.
Rootless/remote Docker bu surumde otomatik ayarlanmaz.

Klasik agent icin .conf dosyasini gercek Include dizinine, genellikle
`/etc/zabbix/zabbix_agentd.d/` altina koyun; ana ayarlar
`/etc/zabbix/zabbix_agentd.conf`, servis `zabbix-agent` olur.

Mount dizininin parent'larinda zabbix kullanicisi traverse iznine sahip olmali.
Collector veri dosyalarini okumaz; mount noktasinda statvfs yapar. Sorun
olursa `sudo -u zabbix stat -f /mnt/web-redis` ile kontrol edin. Redis data
sahipligini zabbix'e cevirmeyin.

## Redis kimlik dogrulama / ACL

Parolasiz local Redis icin auth dosyasi gerekmiyor. AUTH gereken Redis icin
container adina gore ayar dosyasi olusturun:

```bash
install -o root -g zabbix -m 0640 redis-auth.example.json /etc/zabbix/redis-docker/redis.json
editor /etc/zabbix/redis-docker/redis.json
```

`redis.json` adi CONTAINER macro'su ile uyusmali. Parola ve ACL kullanicisini
bu dosyaya yazin. Default kullanici icin username alanini kaldirabilirsiniz.
Ornek monitor kullanicisinin gerekli Redis ACL komut izinleri:

```text
+ping +info +config|get +slowlog|len +slowlog|get
```

Redis ACL icinde bu kullaniciya uygulama anahtarlarini okuma/yazma izni
vermeniz gerekmez. Kullanici/ACL tanimini mevcut Redis yonetim ve kalici
ACL dosyasi yapinizdan yonetin. CONFIG GET izni config okumayi acar;
collector dir ile birlikte yalniz secilmis operasyonel ayarlari sorgular. CONFIG GET dir yasaksa collector alarm verir. Slowlog izinlerini vermek
istemiyorsaniz SLOWLOG.ENABLED=0 yapin; diger kontroller devam eder.
Parola Zabbix macro'suna veya shell argumanina yazilmaz, Redis CLI ortam
degiskeninden alir. Docker/host yonetici yetkisi olanlar ortami gorebilir.

TLS Redis icin JSON'da tls=true yapin. Opsiyonel cacert/cert/key alanlari
container icindeki sertifika yollaridir. Sertifikalar container icinde
mevcut ve redis-cli tarafindan okunabilir olmalidir. Insecure TLS kullanilmaz.

## Import ve dogrulama

1. Sunucu surumune uygun YAML'i Templates > Import ile yukleyin.
2. Template'i Debian hostuna baglayin. Hostta agent interface ve dogru IP:10050 olsun.
3. Host macro'larini container/mount/disk bilgisine gore duzenleyin.
4. Agent kullanicisi ile collector'i test edin:

```bash
sudo -u zabbix /usr/bin/python3 /usr/local/lib/zabbix/redis_docker_collect.py redis /mnt/web-redis/data /mnt/web-redis 6379
```

Beklenen temel alanlar: collector_ok=1, docker_ok=1, container_running=1,
ping_ok=1, mount_ok=1, bind_ok=1; error bos olmali. mount_ok=0 olsa da
collector_ok=1 olabilir: collector calismistir ancak disk alarmi vardir.

Agent 2 uzerinden ayni UserParameter'i dogrulayin:

```bash
sudo -u zabbix zabbix_agent2 -t 'rdm.collect["redis","/mnt/web-redis/data","/mnt/web-redis","6379"]' -c /etc/zabbix/zabbix_agent2.conf
```

Server/proxy tarafindan:

```bash
zabbix_get -s DEBIAN_HOST_IP -p 10050 -k 'rdm.collect["redis","/mnt/web-redis/data","/mnt/web-redis","6379"]'
```

Sonra Latest data'da JSON ve dependent item'larin geldigini kontrol edin.
Birkac ornek sonra 3/5 dakikalik trigger'lar degerlendirilebilir.
Bosta kalan optional alanlarin veri gelmemesi tek basina hata degildir.
Import ekraninda ayni grup zaten varsa mevcut `Templates/Redis Docker`
grubunu kullanin; grup olusturma secenegini kapatip yeniden deneyin.

## V1.1 eklenen Redis izlemesi

Mevcut collector key'i ve dort parametresi, eski item key/UUID'leri, path
makrolari, Docker ve disk kontrolleri korunur. Yeni Redis CPU metrikleri
INFO used_cpu_* sayaclarindan turetilir. Host CPU kapali olsa da bunlar
Redis'in kendi is yukunu izler; host CPU'yu yeniden sorgulamaz. Bir cekirdek
%100'dur; cok cekirdekli Redis'te toplam %100'u asabilir.

Yeni dependent item'lar: Redis trafik byte/s, CPU user/sys/children yuzdeleri,
peak/dataset/overhead/allocator/client/script bellegi, maxmemory-policy,
AOF/RDB sureleri (ilk islemden once -1 olabilir), CoW boyutlari, AOF pending
fsync/rewrite, RDB in-progress, pubsub ve temel replication alanlari.
Eviction, expiry, hit/miss, komut ve connection rate'leri de eklenmistir.
Eski lifetime hit ratio korunur; yeni interval ratio son polling araligindaki
hit/miss rate'lerinden hesaplanir. Islem yoksa interval ratio 0 gosterir;
bu cache sorunu anlamina gelmez.

DB discovery INFO Keyspace'ten db0/db1 vb. DB'leri bulur. Her DB icin keys,
expires (TTL'i olan key sayisi) ve avg_ttl (ms) item'lari vardir. Key isimleri
SCAN/KEYS ile sorgulanmaz. Bos DB INFO'da gorunmeyebilir. Collector arizasinda
kesif unsupported olur; DB'ler yanlislikla silinmez. 6.2 yeni DB/replica LLD
kaynaklarini 7 gun tutar; eski opsiyonel host LLD davranisi korunur.

Slowlog ayri `rdm.slowlog[container,port,enabled]` UserParameter'i kullanir.
SLOWLOG LEN ve SLOWLOG GET 1 cevaplarindan yalniz sayi, son kayit ID/zaman/sure
aktarilir; sorgu metni, argumanlar ve istemci adresi JSON'a aktarilmaz. Yeni
slowlog rate son ID'nin degisiminden hesaplanir, buffer dolu olsa da isler.
Restart ID'yi sifirlayabilir; negatif rate discard edilir. SLOWLOG RESET
bos buffer donerse ID yoktur ve item eski son ID'yi korur. Query gecikmesi
SQL/uygulama uctan uca gecikmesi degil, Redis'in slowlog kaydettigi komut
calisma suresidir. SLOWLOG.ENABLED=0 sorguyu tamamen kapatir.

Secilen config snapshot su alanlari kapsar: maxmemory, maxmemory-policy,
maxclients, appendonly, appendfsync, save, dir, dbfilename, appenddirname,
slowlog-log-slower-than, slowlog-max-len. CONFIG GET * kullanilmaz. Snapshot
JSON'a sirali yazilir; cevap sirasi degisse bile yanlis degisiklik alarmi
olusmaz. Extra query basarisiz olursa config_snapshot_ok=0 olur, ana
collector diger metrikleri toplamaya devam eder. Snapshot Redis 7+ ve
redis-cli --json gerektirir. Redis 6 temel izlemeyi surdurur; config query
uyarisini kapatmak icin CONFIG.CHANGE.ALERT=0 yapin. Ana hedef Redis 7/8'dir.
CONFIG.CHANGE.ALERT=0 alarmi kapatir, Redis 7+ selected config sorgusu devam eder.

Replication standalone kurulumda varsayilan kapali alarmlara sahiptir.
REPLICATION.ENABLED=1 ile masterdaki bagli replica'lar IP:port bazinda
kesfedilir; master offset - replica offset olarak byte lag hesaplanir.
ACK age (slaveN lag) ayri saniye metrigidir. Replica tarafinda master_link_status,
master_last_io_seconds_ago ve sync durumu izlenir. Son iletisim/ACK yasi,
verinin uygulama tarafinda tam olarak kac saniye geride oldugunu kanitlamaz.
Cluster/Sentinel failover/topoloji yonetimi eklenmemistir. INFO replication
alanlari mevcutsa static item'lar toplanir; macro alarm/peer kesfini yonetir.

Yeni alarmlar: fragmentation, Redis surum/role/config degisimi, uptime reset,
yavas docker exec PING, slowlog query/no data/rate ve istege bagli replication.
Docker/collector/port ve disk warning/critical alarmlarina bagimlilik eklendi.
Redis status alarmlari basarisiz collectordan kalan eski degerlerle alarm
uretmemek icin collector_ok kontrolu yapar.

`rdm.redis_ms` ayni key ile korunur; adi Docker exec + redis-cli + PING toplam
sure olarak duzeltildi. Saf Redis network RTT olcumu degildir.

16 normal grafik, DB ve replica graph prototype'lari ile Redis Docker overview
dashboard eklendi. Grafikler Redis CPU, trafik, bellek, keyspace, slowlog,
persistence ve Docker/disk konularini kapsar. Opsiyonel alan yoksa ilgili
grafik serisinde veri olmamasi normaldir. Dashboard Zabbix surumune gore
24/72 sutun widget yapisina uyarlanmistir.

## Metrikler ve alarmlar

Redis: PING/latency, surum/role/uptime, clients/blocked/maxclients/rejected,
used_memory/RSS/maxmemory/fragmentation, evicted/expired keys, hit/miss ve
omur boyu hit ratio, ops/s ve toplam komut/baglanti, latest_fork_usec,
RDB status/last save/changes, AOF enabled/write/rewrite status, rewrite in
progress, current/base size ve delayed fsync.

Docker: API erisimi, running, restart count, container ID degisimi,
healthcheck sonucu. Healthcheck tanimli degilse `none` normaldir. Docker API
kontrolu daemon'un gercek cevap verebildigini olcer; ayri bir systemd service
status kontrolu yapilmaz.

Filesystem: tam mount noktasi, host bind source + writable /data, gercek
Redis dir, read-only flag, doluluk, inode ve kullanilabilir byte.
Bu filesystem sagligi HOST.ENABLED'dan bagimsiz olarak daima izlenir.
Ayni disk zaten Linux template'inde izleniyorsa bu ek filesystem kontrolleri
bilerek kalir; Redis'in dogru diske yazma yapisi icin gereklidir.

Kritik alarmlar: mount yok, Docker erisilemiyor, container calismiyor,
PING basarisiz, yanlis bind/Redis dir, read-only filesystem, disk/inode
critical, AOF/RDB err, zorunlu AOF kapali. Collector veri gelmeme 5 dakika,
basarisizliklar 3 dakika, disk/kaynak esikleri 5 dakika ile degerlendirilir.
Container restart/recreation, rejected connection ve delayed fsync artisinda
alarm gelir. Eviction alarmi macro ile istege baglidir. `blocked_clients > 0`
BLPOP gibi is yuklerinde normal olabildiginden otomatik alarm konulmadi.

maxmemory=0 iken maxmemory kullanim yuzdesi uretilemez; RAM izlemesini
ayrica acin veya mevcut Linux template'ini kullanin. INFO'da olmayan
opsiyonel alanlar DISCARDED olur, sifir/saglikli diye uydurulmaz. AOF kapali
oldugunda AOF status alarmlari degerlendirilmez. Sayac resetinde negatif
change alarm yapmaz. Cache hit ratio son dakika degil Redis uptime boyunca
birikmis orandir.

Opsiyonel disk IO host device duzeyindedir, yalniz Redis'e ait degildir.
Latency /sys/block/DEVICE/stat toplam IO sureleri ve tamamlanan IO sayilarinin
saniyelik degisimlerinden ms/operation olarak hesaplanir. DEVICE regex'ini
`lsblk` ile veri diskinize gore secin. Partition yerine sdb/nvme0n1 gibi
block device kullanin; filesystem path'inden device otomatik eslestirilmez.

Bu template mount problemi icin alarm uretir; container'in baslamasini
engellemez. NTP, SSH, backup/restore ve cluster failover izlemesi dahil degildir.
Tam host kapsami gerekiyorsa mevcut Linux template'inizi kullanin ve
HOST.ENABLED=0 birakin.

## Yerel dogrulama

Collector yalniz Python stdlib kullanir. Paket testlerini yeniden calistirmak
icin Python PyYAML ve Node.js gerekir; bunlar hedef hosttaki collector icin
zorunlu degildir.


`python test_monitor.py`: 29 test gecti. Redis/Docker cevap fixture'lari ile
saglikli akis, mount yoklugu, yanlis bind/Redis dir, AUTH/INFO reddi, container
kaybi/durmasi, Docker arizasi, maxmemory=0/AOF kapali, parametre kontrolu ve
parolanin argumanlara konmamasi test edildi. Uc YAML parse edildi; LLD
anahtarlari, macro kapatma/acma JavaScript'i ve disk counter cikarma islemi
Node ile calistirildi. Yeni DB/replica/config/slowlog akislarinin yaninda
mevcut item key/UUID korumasi, 32 karakter UUID formati, macro tanimlari,
grafik referanslari, dashboard grid ve trigger dependency dongusuzlugu da
kontrol edildi. 7.0/7.4 widget formati resmi Zabbix Redis YAML
dosyalarindaki graph/graphid.0/reference yapisiyla karsilastirildi.

Bu ortamda Docker veya Zabbix sunucu/agent bulunmadigi icin canli container,
Zabbix import/API ve gercek passive ag sorgusu testi yapilmadi. Kurulumdan
sonra yukaridaki host kontrollerini uygulayin. YAML parse testi tek basina
Zabbix importunun basarili oldugunu kanitlamaz.

## Kaynaklar

- https://www.zabbix.com/documentation/6.2/en/manual/xml_export_import
- https://www.zabbix.com/documentation/6.2/en/manual/api/reference/configuration/import
- https://www.zabbix.com/documentation/6.2/en/manual/config/items/itemtypes/zabbix_agent
- https://www.zabbix.com/documentation/7.0/en/manual/xml_export_import/hosts
- https://www.zabbix.com/documentation/7.4/en/manual/xml_export_import/templates
- https://redis.io/docs/latest/commands/info/
