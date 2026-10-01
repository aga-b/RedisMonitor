# V1.0.0 -> V1.1.0 guncelleme

Template'in mevcut yapisi korunur: ayni ad/UUID, ayni eski item key/UUID'leri,
passive agent, ayni rdm.collect dort parametresi, Docker/disk kontrolleri ve
host makrolari. Yeni collector ve UserParameter dosyasini YAML'den once
kurun. Redis container veya data dizininde degisiklik gerekmez.

1. Mevcut template'i Zabbix'ten export ederek yedekleyin.
2. Hedef Debian'da paket dizininde root olarak:

```bash
cp /usr/local/lib/zabbix/redis_docker_collect.py /usr/local/lib/zabbix/redis_docker_collect.py.v1.0.0
cp /etc/zabbix/zabbix_agent2.d/redis_docker.conf /etc/zabbix/zabbix_agent2.d/redis_docker.conf.v1.0.0
install -m 0755 redis_docker_collect.py /usr/local/lib/zabbix/redis_docker_collect.py
install -m 0644 redis_docker.conf /etc/zabbix/zabbix_agent2.d/redis_docker.conf
systemctl restart zabbix-agent2
```

Agent timeout en az 15 saniye olmali. Klasik agent'ta Include dizinini,
config yolunu ve restart servisini zabbix-agent olarak uyarlayin.
Config `.v1.0.0` yedegi `.conf` ile bitmez; *.conf Include'a ikinci kez girmez.

3. AUTH/ACL varsa monitor kullanicisina `+slowlog|len +slowlog|get` ekleyin.
   Mevcut `+ping +info +config|get` izinleri korunur. Slowlog istemiyorsaniz
   host macro'sunda `{$REDIS.SLOWLOG.ENABLED}=0` yapin.
4. Sunucu versiyonuna uygun 6.2 / 7.0 / 7.4 YAML'i import edin. Update existing
   template/items/discovery/triggers/graphs/dashboard/macros ve yeni kaynaklar
   icin Create new seceneklerini acin; Delete missing seceneklerini kapali tutun.
   Grup zaten varsa grup icin Create new'u kapatin. Ayni hosta ucunu baglamayin.
5. Host seviyesindeki container adi, DATA.PATH/MOUNT.PATH ve host izleme
   tercihlerini koruyun. Template macro varsayilanlari host override'larini
   degistirmez. HOST.ENABLED varsayilan yine 0'dur.
6. Test komutlarinda `redis` yerine gercek container adinizi yazin:

```bash
sudo -u zabbix /usr/bin/python3 /usr/local/lib/zabbix/redis_docker_collect.py redis /mnt/web-redis/data /mnt/web-redis 6379
sudo -u zabbix /usr/bin/python3 /usr/local/lib/zabbix/redis_docker_collect.py --slowlog redis 6379 1
```

Ana JSON'da collector_ok/docker_ok/container_running/ping_ok/mount_ok/bind_ok=1
beklenir. Extra config sorgusunda config_snapshot_ok=1 beklenir. Slowlog JSON'da
ok=1; buffer bossa last_id gelmemesi normaldir. Kimlik dogrulama dosyasi adi
container adiyla eslesmeye devam eder.

7. Latest data, Discovery ve Redis Docker overview dashboard'u kontrol edin.
   Rate metrikleri ilk ornekten sonra veri uretir; DB bos ise kesif listesi bos
   olabilir. Replication kuruluysa `{$REDIS.REPLICATION.ENABLED}=1` yapin.

Host metriklerini 6.2'de acip sonradan kapatmak mevcut davranis geregi ilgili
kesfedilmis host item'larini ve gecmislerini siler. Guncelleme bunlari varsayilan
olarak acmaz. Yeni DB/replica discovery icin lost lifetime 7 gundur.

Geri donus: export yedegi ve eski collector/conf dosyalarini geri yukleyin.
V1.1 YAML'i eski collector ile birakirsaniz yeni slowlog key'i unsupported olur.
