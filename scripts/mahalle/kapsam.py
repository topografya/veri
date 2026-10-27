#!/usr/bin/env python3
"""
Mahalle ve köy kapsam raporu: TÜİK'in mahalle/köy listesini (ADNKS 2025, MEDAS) OpenStreetMap'teki mahalle ve köy
sınırları (boundary=administrative, admin_level 8–10; place alanları) ve noktalarıyla (place=village, neighbourhood,
suburb, quarter, hamlet) ilçe ilçe ad üzerinden eşleştirir. Her ilçe için hangi gösterimin (sınır / nokta) mümkün
olduğunu sınıflar. Bu betik veri üretmez; yalnız rapor yazar.

Kullanım:
  kapsam.py <süzülmüş.osm.pbf> <ilce-ham.geojson> <medas_mahalle.csv> <medas_koy.csv> <çıktı klasörü>
"""
import csv, json, os, re, sys, unicodedata, collections
import osmium
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

ADMIN = {"8", "9", "10"}
PLACE_N = {"village": 1, "neighbourhood": 2, "suburb": 2, "quarter": 2, "hamlet": 3, "town": 2}
PLACE_A = {"village", "neighbourhood", "suburb", "quarter", "hamlet"}
EK = re.compile(r"\b(mahallesi|mahalle|mah|mh|koyu|koy|beldesi|belde)\b\.?", re.I)


def kucuk(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


def norm(s):
    """Ad karşılaştırma anahtarı: küçük harf, Türkçe karakter ve ekler ("Mah.", "Köyü") atılmış, yalnız harf/rakam."""
    s = kucuk(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("ı", "i")
    s = EK.sub(" ", s)
    return re.sub(r"[^a-z0-9]", "", s)


# ---------- TÜİK ----------
def tuik_oku(yol, tur):
    rx = re.compile(r"^(.+?)\((.+?)/(.+?)/(.+)\)-(\d+)$") if tur == "mahalle" else re.compile(r"^(.+?)\((.+?)/(.+)\)-(\d+)$")
    out = []
    with open(yol, encoding="utf-8-sig") as f:
        for ln in f:
            p = ln.rstrip("\n").split("|")
            if len(p) < 3:
                continue
            m = rx.match(p[1])
            if not m:
                continue
            g = m.groups()
            if tur == "mahalle":
                il, ilce, bel, ad, kod = g
            else:
                il, ilce, ad, kod = g
                bel = ""
            out.append({"tur": tur, "il": il, "ilce": ilce, "belediye": bel, "ad": ad, "kod": int(kod), "nufus": int(float(p[2] or 0))})
    return out


# ---------- OSM ----------
class Toplayici(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.fab = osmium.geom.GeoJSONFactory()
        self.ogeler = []  # {tip: poligon|nokta, kaynak, ad, osm, geom}

    def node(self, n):
        pl = n.tags.get("place")
        if pl in PLACE_N and n.tags.get("name"):
            self.ogeler.append({"tip": "nokta", "kaynak": "place=" + pl, "oncelik": PLACE_N[pl], "ad": n.tags.get("name:tr") or n.tags["name"],
                                "osm": "node/%d" % n.id, "geom": Point(n.location.lon, n.location.lat)})

    def area(self, a):
        t = a.tags
        ad = t.get("name:tr") or t.get("name")
        if not ad:
            return
        adm = t.get("boundary") == "administrative" and t.get("admin_level") in ADMIN
        pl = t.get("place") in PLACE_A
        if not (adm or pl):
            return
        if any(k.k.startswith(("disused:", "was:", "abandoned:")) for k in t) or "end_date" in t:
            return
        try:
            g = shape(json.loads(self.fab.create_multipolygon(a)))
        except Exception:
            return
        if g.is_empty:
            return
        kaynak = ("admin_level=" + t.get("admin_level")) if adm else ("place=" + t.get("place"))
        osm = ("way/%d" if a.from_way() else "relation/%d") % a.orig_id()
        self.ogeler.append({"tip": "poligon", "kaynak": kaynak, "oncelik": 0 if adm else 1, "ad": ad, "osm": osm, "geom": g})


def main():
    pbf, ilce_gj, mah_csv, koy_csv, cikti = sys.argv[1:6]
    os.makedirs(cikti, exist_ok=True)

    # İlçe poligonları (derle.py çıktısı; resmî adlarla)
    ilceler = json.load(open(ilce_gj, encoding="utf-8"))["features"]
    poly = [shape(f["geometry"]) for f in ilceler]
    agac = STRtree(poly)
    anahtar = [(norm(f["properties"]["il_adi"]), norm(f["properties"]["ilce_adi"])) for f in ilceler]
    il_of = {}  # norm(il) → set(norm(ilçe))
    for k in anahtar:
        il_of.setdefault(k[0], set()).add(k[1])

    def ilce_bul(geom):
        p = geom if geom.geom_type == "Point" else geom.representative_point()
        for i in agac.query(p):
            if poly[i].contains(p):
                return anahtar[i]
        return None

    # TÜİK ilçe adı → OSM ilçe anahtarı ("Merkez" → "<İl> Merkez"; yinelenen ad önekli; doğrudan ad)
    def tuik_ilce(il, ilce):
        i, c = norm(il), norm(ilce)
        aday = il_of.get(i, set())
        for k in (c, i + "merkez" if c == "merkez" else None, i + c):
            if k and k in aday:
                return (i, k)
        return None

    birimler = tuik_oku(mah_csv, "mahalle") + tuik_oku(koy_csv, "koy")
    eslesmeyen_ilce = collections.Counter()
    for b in birimler:
        b["anahtar"] = tuik_ilce(b["il"], b["ilce"])
        if not b["anahtar"]:
            eslesmeyen_ilce[(b["il"], b["ilce"])] += 1

    t = Toplayici()
    t.apply_file(pbf, locations=True, idx="flex_mem")
    osm_ilce = collections.defaultdict(lambda: collections.defaultdict(list))  # anahtar → norm(ad) → [öğe]
    disarida = 0
    for o in t.ogeler:
        k = ilce_bul(o["geom"])
        if not k:
            disarida += 1
            continue
        o["ilce"] = k
        osm_ilce[k][norm(o["ad"])].append(o)

    # Eşleştirme: aynı ilçede, aynı ad anahtarı. Önce poligon, yoksa nokta. Bir OSM öğesi tek birime verilir.
    kullanildi = set()
    satirlar = []
    sayac = collections.defaultdict(lambda: collections.Counter())
    for b in birimler:
        k = b["anahtar"]
        s = sayac[k if k else ("?", norm(b["il"]) + "/" + norm(b["ilce"]))]
        s["n"] += 1
        s["nufus"] += b["nufus"]
        sonuc, osm, kaynak = "yok", "", ""
        if k:
            adaylar = [o for o in osm_ilce[k].get(norm(b["ad"]), []) if o["osm"] not in kullanildi]
            pol = sorted([o for o in adaylar if o["tip"] == "poligon"], key=lambda o: o["oncelik"])
            nok = sorted([o for o in adaylar if o["tip"] == "nokta"], key=lambda o: o["oncelik"])
            if pol:
                sonuc, o = ("poligon" if len(pol) == 1 or pol[0]["oncelik"] < pol[1]["oncelik"] else "poligon_cok_aday"), pol[0]
            elif nok:
                sonuc, o = ("nokta" if len(nok) == 1 or nok[0]["oncelik"] < nok[1]["oncelik"] else "nokta_cok_aday"), nok[0]
            if sonuc != "yok":
                kullanildi.add(o["osm"])
                osm, kaynak = o["osm"], o["kaynak"]
        s[sonuc] += 1
        s[sonuc + "_nufus"] += b["nufus"]
        satirlar.append([b["tur"], b["kod"], b["il"], b["ilce"], b["belediye"], b["ad"], b["nufus"], sonuc, osm, kaynak])

    # Kullanılmayan OSM öğeleri (ad iyileştirmesi incelemesi için)
    with open(os.path.join(cikti, "osm_kullanilmayan.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["il", "ilce", "tip", "kaynak", "ad", "osm"])
        for k, d in osm_ilce.items():
            for lst in d.values():
                for o in lst:
                    if o["osm"] not in kullanildi:
                        w.writerow([k[0], k[1], o["tip"], o["kaynak"], o["ad"], o["osm"]])
    with open(os.path.join(cikti, "eslesme.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tur", "tuik_kod", "il", "ilce", "belediye", "ad", "nufus_2025", "sonuc", "osm", "osm_kaynak"])
        w.writerows(satirlar)

    def sinif(s):
        n = s["n"] or 1
        p = (s["poligon"] + s["poligon_cok_aday"]) / n
        q = p + (s["nokta"] + s["nokta_cok_aday"]) / n
        if p >= 0.95:
            return "sinir_tam"
        if p >= 0.5:
            return "sinir_kismi"
        if q >= 0.9:
            return "nokta"
        return "zayif"

    ilce_satir, siniflar, sinif_nufus = [], collections.Counter(), collections.Counter()
    ad_of = {}
    for b in birimler:
        ad_of.setdefault(b["anahtar"], (b["il"], b["ilce"]))
    for k, s in sorted(sayac.items(), key=lambda kv: ad_of.get(kv[0], kv[0])):
        il, ilce = ad_of.get(k, k)
        sn = sinif(s)
        siniflar[sn] += 1
        sinif_nufus[sn] += s["nufus"]
        fazla = sum(1 for lst in osm_ilce.get(k, {}).values() for o in lst if o["tip"] == "poligon" and o["osm"] not in kullanildi)
        ilce_satir.append([il, ilce, s["n"], s["nufus"], s["poligon"], s["poligon_cok_aday"], s["nokta"], s["nokta_cok_aday"], s["yok"], fazla, sn])
    with open(os.path.join(cikti, "kapsam_ilce.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["il", "ilce", "tuik_birim", "nufus_2025", "poligon", "poligon_cok_aday", "nokta", "nokta_cok_aday", "yok", "osm_fazla_poligon", "sinif"])
        w.writerows(ilce_satir)

    top = collections.Counter()
    for s in sayac.values():
        top.update(s)
    ozet = {
        "tuik_birim": len(birimler), "tuik_nufus": sum(b["nufus"] for b in birimler),
        "osm_oge": {"poligon": sum(1 for o in t.ogeler if o["tip"] == "poligon"), "nokta": sum(1 for o in t.ogeler if o["tip"] == "nokta"), "ilce_disinda": disarida},
        "sonuc_birim": {k: top[k] for k in ("poligon", "poligon_cok_aday", "nokta", "nokta_cok_aday", "yok")},
        "sonuc_nufus": {k: top[k + "_nufus"] for k in ("poligon", "poligon_cok_aday", "nokta", "nokta_cok_aday", "yok")},
        "ilce_sinif": dict(siniflar), "ilce_sinif_nufus": dict(sinif_nufus),
        "eslesmeyen_tuik_ilce": [list(k) + [v] for k, v in eslesmeyen_ilce.items()],
    }
    json.dump(ozet, open(os.path.join(cikti, "kapsam_ozet.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(ozet, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
