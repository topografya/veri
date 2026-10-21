# Topografya Açık Veri

[topografya.com.tr](https://topografya.com.tr) araçlarının kullandığı açık coğrafi veriler. Veriler OpenStreetMap'ten otomatik olarak derlenir, denetlenir ve her ay güncellenir.

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

Kalıcı bağlantılar için sürüm etiketini (`@v…`) kullanın; `@latest` en yeni sürümü verir.

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
