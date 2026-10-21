#!/usr/bin/env python3
"""
Hat testi için yapay OSM verisi üretir (gerçek veri değildir).
81 il (9x9 ızgara) x 12 ilçe (4x3) = 972 ilçe; komşu birimler aynı yolları paylaşır.
Kenarlar ±8 m gürültülüdür (30 m sadeleştirmede yok olmalı). Bir komşu ülke ilişkisi (GR) ve
il dışı bir ilçe ilişkisi eklenir (süzülmeli). Kara poligonu güneybatı köşeyi denize bırakır.
Kullanım: yapay_osm.py <cikti.osm> <kara.shp-öneki>
"""
import sys, math, random
import shapefile

random.seed(42)
osm_yol, kara_onek = sys.argv[1], sys.argv[2]
LON0, LAT0, NX, NY = 26.0, 35.9, 36, 27     # ilçe ızgarası
DX, DY = 18.0 / NX, 6.3 / NY
nid = [0]; nodes = []; ways = []; rels = []

def yeni_nokta(lon, lat):
    nid[0] += 1; nodes.append((nid[0], lon, lat)); return nid[0]

kose = {}
for i in range(NX + 1):
    for j in range(NY + 1):
        kose[(i, j)] = yeni_nokta(LON0 + i * DX, LAT0 + j * DY)

wid = [1000000]
yollar = {}
def kenar(a, b):
    """a, b ızgara köşeleri; aradaki yol (gürültülü ara noktalarla), paylaşımlı."""
    key = tuple(sorted([a, b]))
    if key in yollar: return yollar[key]
    (i1, j1), (i2, j2) = key
    lon1, lat1 = LON0 + i1 * DX, LAT0 + j1 * DY; lon2, lat2 = LON0 + i2 * DX, LAT0 + j2 * DY
    ref = [kose[key[0]]]
    n = 40
    for k in range(1, n):
        t = k / n
        # ±8 m dik gürültü (derece cinsinden yaklaşık)
        g = (random.random() - 0.5) * 16 / 111320
        if i1 == i2: ref.append(yeni_nokta(lon1 + g / math.cos(math.radians(lat1)), lat1 + t * (lat2 - lat1)))
        else: ref.append(yeni_nokta(lon1 + t * (lon2 - lon1), lat1 + g))
    ref.append(kose[key[1]])
    wid[0] += 1; ways.append((wid[0], ref)); yollar[key] = wid[0]
    return wid[0]

def hucre_yollari(i0, j0, i1, j1):
    """[i0,i1]x[j0,j1] dikdörtgeninin çevresindeki ızgara kenarları."""
    w = []
    for i in range(i0, i1): w.append(kenar((i, j0), (i + 1, j0))); w.append(kenar((i, j1), (i + 1, j1)))
    for j in range(j0, j1): w.append(kenar((i0, j), (i0, j + 1))); w.append(kenar((i1, j), (i1, j + 1)))
    return w

rid = [2000000]
il_no = 0
for gy in range(9):
    for gx in range(9):
        il_no += 1
        kod = '%02d' % il_no
        rid[0] += 1
        rels.append((rid[0], hucre_yollari(gx * 4, gy * 3, gx * 4 + 4, gy * 3 + 3), {'boundary': 'administrative', 'admin_level': '4', 'type': 'boundary', 'name': 'İl %s' % kod, 'ISO3166-2': 'TR-' + kod, 'wikidata': 'Q%d' % (1000 + il_no)}))
        for sy in range(3):
            for sx in range(4):
                i, j = gx * 4 + sx, gy * 3 + sy
                rid[0] += 1
                rels.append((rid[0], hucre_yollari(i, j, i + 1, j + 1), {'boundary': 'administrative', 'admin_level': '6', 'type': 'boundary', 'name': 'İlçe %s-%d%d' % (kod, sx, sy), 'wikidata': 'Q%d' % (500000 + il_no * 100 + sx * 10 + sy)}))
# mükerrer (eski) ilçe ilişkisi: 48 nolu ilin ilk ilçesiyle aynı sınır (ayıklanmalı)
eski = [r for r in rels if r[2].get('name') == 'İlçe 48-00'][0]
rid[0] += 1; rels.append((rid[0], list(eski[1]), {'boundary': 'administrative', 'admin_level': '6', 'type': 'boundary', 'name': 'Eski ilçe 48'}))
# kullanımdan kalkmış işaretli ilişki (en baştan süzülmeli)
rid[0] += 1; rels.append((rid[0], list(eski[1]), {'boundary': 'administrative', 'admin_level': '6', 'type': 'boundary', 'name': 'Kapanmış ilçe', 'end_date': '2012'}))
# komşu ülke birimi (süzülmeli) ve il dışında ilçe (süzülmeli)
ga = yeni_nokta(20.0, 39.0); gb = yeni_nokta(21.0, 39.0); gc = yeni_nokta(21.0, 40.0); gd = yeni_nokta(20.0, 40.0)
wid[0] += 1; ways.append((wid[0], [ga, gb, gc, gd, ga]))
rid[0] += 1; rels.append((rid[0], [wid[0]], {'boundary': 'administrative', 'admin_level': '4', 'type': 'boundary', 'name': 'Komşu', 'ISO3166-2': 'GR-A'}))
rid[0] += 1; rels.append((rid[0], [wid[0]], {'boundary': 'administrative', 'admin_level': '6', 'type': 'boundary', 'name': 'Komşu ilçe'}))

def esc(s): return s.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')
with open(osm_yol, 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="yapay">\n')
    for i, lon, lat in nodes: f.write('<node id="%d" version="1" lat="%.7f" lon="%.7f"/>\n' % (i, lat, lon))
    for w, refs in ways: f.write('<way id="%d" version="1">' % w + ''.join('<nd ref="%d"/>' % r for r in refs) + '</way>\n')
    for r, ws, tags in rels:
        f.write('<relation id="%d" version="1">' % r + ''.join('<member type="way" ref="%d" role="outer"/>' % w for w in ws) + ''.join('<tag k="%s" v="%s"/>' % (k, esc(v)) for k, v in tags.items()) + '</relation>\n')
    f.write('</osm>\n')

# Kara: tüm kapsam, güneybatıdaki üçgen deniz (26–29.5 D, 35.9–37.3 K arası köşegen altı)
w = shapefile.Writer(kara_onek, shapeType=shapefile.POLYGON); w.field('FID', 'N', 9, 0)
dis = [[25.0, 35.0], [25.0, 43.0], [46.0, 43.0], [46.0, 35.0], [29.5, 35.0], [25.0, 37.3], [25.0, 35.0]]
w.poly([dis]); w.record(1)  # dış halka saat yönünde (Shapefile kuralı)
w.close()
print('düğüm', len(nodes), 'yol', len(ways), 'ilişki', len(rels))
