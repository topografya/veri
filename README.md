# Topografya Açık Veri

[topografya.com.tr](https://topografya.com.tr) araçlarının kullandığı açık coğrafi veriler: il ve ilçe sınırları, nüfus göstergeleri, mahalle ve köy nüfusu. Sınırlar OpenStreetMap'ten, nüfus TÜİK'ten alınır; hepsi her ay `.github/workflows/sinirlar.yml` ile birlikte derlenir, denetlenir ve `yayin` dalına sürüm etiketiyle yazılır.

## Türkiye il ve ilçe sınırları

81 il ve tüm ilçelerin idari sınır poligonları (OpenStreetMap, `admin_level` 4 ve 6).

| Dosya | İçerik | Tolerans |
|---|---|---|
| `sinirlar/ozet.json` | İl ve ilçe listesi, plaka kodu, jeodezik alan (km²), kapsam kutusu, veri tarihi | – |
| `sinirlar/il.topo.json` | İller | ≈ 30 m |
| `sinirlar/il-sade.topo.json` | İller (ülke ölçeği) | ≈ 500 m |
| `sinirlar/ilce-sade.topo.json` | Tüm ilçeler (ülke ölçeği) | ≈ 500 m |
| `sinirlar/ilce/NN.topo.json` | NN plaka kodlu ilin ilçeleri | ≈ 30 m |

Biçim: [TopoJSON](https://github.com/topojson/topojson-specification), WGS84 (EPSG:4326). Dosyalar `yayin` dalında ve sürüm etiketlerindedir (`vYIL.AY.N`).

**Kullanım (CDN):**

    https://cdn.jsdelivr.net/gh/topografya/veri@latest/sinirlar/ozet.json
    https://cdn.jsdelivr.net/gh/topografya/veri@v2026.10.0/sinirlar/ilce/06.topo.json

Kalıcı bağlantılar için sürüm etiketini (`@v…`) kullanın; `@latest` en yeni sürümü verir. topografya.com.tr araçları denetlenmiş bir sürüm etiketine bağlıdır; yeni ayın verisi denetlendikten sonra araçlar yeni sürüme geçirilir.

**Öznitelikler:** `il_kodu` (plaka), `il_adi`, `ilce_adi`, `alan_km2` (WGS84 elipsoidi üzerinde jeodezik alan, kıyıdan kırpılmış), `wikidata`, `osm_id`; il katmanında ayrıca `ilce_sayisi`.

### Yöntem

1. Geofabrik Türkiye OSM kesiti indirilir, MD5 ile doğrulanır.
2. `boundary=administrative` ilişkileri süzülür; iller `ISO3166-2 = TR-NN` etiketiyle, ilçeler temsil noktalarının düştüğü ile göre seçilir.
3. Deniz alanları OSM kara poligonlarıyla kıyı çizgisinden kırpılır; göller korunur.
4. Alanlar WGS84 elipsoidi üzerinde jeodezik olarak hesaplanır (Karney, 2013).
5. İlçeler ortak topoloji üzerinde Douglas–Peucker yöntemiyle sadeleştirilir; iller sadeleştirilmiş ilçelerin birleştirilmesiyle üretilir. Böylece komşu birimler arasında boşluk ya da bindirme oluşmaz, il ve ilçe sınırları birebir çakışır.
6. Yayından önce bağımsız denetim çalışır: il sayısı 81, ilçe sayısı 950–1000, her ilin ilçeleri ilin alanını %0,5 içinde karşılamalı, bindirme olmamalı. Eşik aşılırsa yayın yapılmaz.

### Sınırlılıklar

Bu sınırlar **resmî değildir**. OpenStreetMap gönüllülerce oluşturulur; yerel farklar onlarca metreye ulaşabilir. Tapu, kadastro, imar ve hukuki işlerde Harita Genel Müdürlüğü, Tapu ve Kadastro Genel Müdürlüğü ve ilgili idarelerin resmî kayıtları esastır. İlçelerin resmî kodları OSM'de bulunmadığından verilmez.

## Lisans

Veri: **© OpenStreetMap katkıcıları**, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Betikler: MIT. Ayrıntılar [LISANS.md](LISANS.md).

## Geliştirme

    pip install osmium==4.0.2 shapely==2.0.6 pyproj==3.7.0 pyshp==2.3.1
    npm ci --prefix scripts/sinirlar
    python scripts/sinirlar/test/yapay_osm.py /tmp/yapay.osm /tmp/kara
    python scripts/sinirlar/derle.py /tmp/yapay.osm /tmp/ham --kara /tmp/kara.shp
    node scripts/sinirlar/yayinla.mjs /tmp/ham /tmp/sinirlar
    node scripts/sinirlar/test/denetle.mjs /tmp/sinirlar --yapay

## Türkiye nüfus ve demografi göstergeleri (TÜİK)

TÜİK Adrese Dayalı Nüfus Kayıt Sistemi (ADNKS) sonuçlarından il ve ilçe göstergeleri; ilçeler yukarıdaki sınırlarla `osm_id` üzerinden eşleştirilmiştir.

| Dosya | İçerik |
|---|---|
| `nufus/gostergeler.json` | Türkiye ve 81 il: 2007–2025 nüfus, artış hızı (‰), ortanca yaş (toplam/erkek/kadın), yaş bağımlılık oranları, 0–14 ve 65+ oranı, cinsiyet oranı, 2008–2025 ortalama hanehalkı büyüklüğü, merkez/belde-köy nüfusu; 973 ilçe: 2024–2025 nüfus, merkez/belde-köy nüfusu, artış hızı, OSM alanı. Türkiye için medeni durum. |
| `nufus/piramit.json` | Türkiye ve 81 il, 2007–2025, 19 yaş grubu × cinsiyet nüfusu |

**Kaynak:** TÜİK Veri Portalı, Toplu Veri Seti İndirme (CSV): DF_ADNKS_T16, T21, T22, T23, T24, T25, T38. TÜİK verileri kaynak gösterilerek izin gerekmeksizin yeniden kullanılabilir (TÜİK Yasal Uyarı). Atıf: "Kaynak: TÜİK, Adrese Dayalı Nüfus Kayıt Sistemi".

**Üretim:** `scripts/nufus/hazirla.py`; girdi `scripts/nufus/ham/` (TÜİK Veri Portalı toplu indirmeden alınan özgün CSV dosyaları, 2025 yayını). İlçe adı eşleştirme denetimi: `scripts/nufus/eslestir.py`. Denetimler: yaş-cinsiyet toplamı = il nüfusu, ilçe toplamı = il nüfusu, merkez + belde/köy = toplam, her ilin ilçe sayısı OSM ile aynı. 10 ilçede adlar otomatik eşleşmez; eşleştirme `hazirla.py` içindeki `ELLE` sözlüğünde elle tanımlıdır, çıktıda TÜİK adı kullanılır:

| İl | TÜİK adı | OSM adı | Neden |
|---|---|---|---|
| Amasya | Amasya Merkez | Amasya | "Merkez" eki |
| Çanakkale | Çanakkale Merkez | Çanakkale | "Merkez" eki |
| Iğdır | Iğdır Merkez | Iğdır | "Merkez" eki |
| Siirt | Siirt Merkez | Siirt | "Merkez" eki |
| Tokat | Tokat Merkez | Tokat | "Merkez" eki |
| Uşak | Uşak Merkez | Uşak | "Merkez" eki |
| Ağrı | Patnos | Panos | OSM yazım hatası |
| Kırıkkale | Balışeyh | Balışıh | OSM yazım farkı |
| Tunceli | Nazımiye | Nazmiye | OSM yazım farkı |
| Yozgat | Sarıkaya | Sarıkaya Deresi | OSM sınır adı |

Her eşleşme ilçe sayısı ve ilçe toplamı = il nüfusu denetimleriyle doğrulanır; bir eşleşme bozulursa betik durur. Artış hızı 2024–2025 için TÜİK tablosundan, önceki yıllar ln(Pt/Pt−1)×1000 ile hesaplanır.

## Mahalle ve köy nüfusu (TÜİK + OpenStreetMap)

| Dosya | İçerik |
|---|---|
| `mahalle/ozet.json` | İl ve ilçe listesi; her ilçede birim sayısı, sınırlı/noktalı/geometrisiz birim sayısı, nüfus, dosya boyutu |
| `mahalle/NN/<ilçe osm_id>.geojson` | Bir ilçenin bütün mahalle ve köyleri: `k` TÜİK kodu, `a` ad, `t` m/k (mahalle/köy), `b` belediye, `i` ilçe, `n` 2025 nüfusu, `g` s/n/- (sınır/nokta/yok), `o` OSM kimliği; sınırlılarda `c` temsil noktası ve `km2` |

**Nüfus:** TÜİK Merkezi Dağıtım Sistemi, ADNKS 2025, belediye, köy ve mahalle nüfusları (32.254 mahalle, 18.183 köy; ham dosyalar `scripts/nufus/ham/mahalle/`). TÜİK mahalle düzeyinde cinsiyet ve yaş yayımlamaz.

**Konum ve sınır:** Her TÜİK birimi aynı ilçe içinde aynı adlı OSM sınırıyla (admin_level 8–10 ya da `place` alanı) eşleştirilir; sınır yoksa OSM noktası, o da yoksa geometrisiz kayıt verilir. Tahmini (Voronoi vb.) sınır üretilmez. Sınırlar resmî değildir. Üretim: `scripts/mahalle/kapsam.py` (eşleştirme ve kapsam raporu), `scripts/mahalle/uret.py` (ilçe dosyaları ve kalite denetimi); raporlar iş akışının çıktı dosyalarında saklanır.
