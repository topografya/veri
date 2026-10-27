#!/usr/bin/env python3
"""
Türkiye il ve ilçe sınırları - OpenStreetMap'ten derleme (1. aşama)

Girdi : OSM dosyası (.osm.pbf ya da .osm), isteğe bağlı kara poligonları (land-polygons-split-4326 .shp)
Çıktı : <cikti>/ilce-ham.geojson   ilçe poligonları (kırpılmış, öznitelikli, alanlı)
        <cikti>/il-ham.geojson     il poligonları (OSM il ilişkilerinden; yalnız denetim ve öznitelik için)
        <cikti>/derleme.json       sayılar, tarih, denetim sonuçları

Kurallar
- İl  : boundary=administrative + admin_level=4 + ISO3166-2 = TR-NN (NN plaka kodu)
- İlçe: boundary=administrative + admin_level=6, temsil noktası bir ilin içinde kalan
- Denizler: kara poligonu verilirse kıyı çizgisinden kırpılır (göller korunur)
- Alan : WGS84 elipsoidi üzerinde jeodezik alan (pyproj.Geod, Karney 2013)

Lisans: Veri © OpenStreetMap katkıcıları, ODbL 1.0. Bu betik MIT.
"""
import argparse, json, os, re, sys, datetime
import osmium
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import make_valid
from pyproj import Geod

GEOD = Geod(ellps="WGS84")
TR_BBOX = (25.4, 35.6, 45.0, 42.3)  # boylam/enlem kapsamı (kara + kıyı)
# OSM adı resmî ilçe adından farklı olan ilçeler (OSM yazım hatası ya da "Merkez" ekinin eksikliği).
# Resmî ad: TÜİK ADNKS il/ilçe tabloları ve İçişleri Bakanlığı ilçe listesi. OSM'deki ad "osm_ad" özniteliğinde korunur.
# Anahtar OSM ilişki kimliğidir; kimlik değişirse eşleme sessizce boşa düşer ve aşağıdaki denetim uyarır.
RESMI_AD = {
    1780615: "Patnos",          # Ağrı — OSM: Panos
    1829326: "Nazımiye",        # Tunceli — OSM: Nazmiye
    1251198: "Balışeyh",        # Kırıkkale — OSM: Balışıh
    1561850: "Sarıkaya",        # Yozgat — OSM: Sarıkaya Deresi
    3668268: "Yunusemre",       # Manisa — OSM: Yunus Emre
    1837141: "Amasya Merkez", 1816280: "Çanakkale Merkez", 1246473: "Siirt Merkez",
    1804178: "Tokat Merkez", 1609669: "Uşak Merkez", 1251330: "Iğdır Merkez",
}
ISO_RE = re.compile(r"^TR-(\d{2})$")


def jeodezik_alan_km2(geom):
    """Jeodezik alan (km²). Poligon dış halkası pozitif, delikler negatif sayılır."""
    def poly_alan(p):
        a, _ = GEOD.geometry_area_perimeter(p)
        return abs(a)
    if geom.geom_type == "Polygon":
        return poly_alan(geom) / 1e6
    return sum(poly_alan(p) for p in geom.geoms) / 1e6


def poligonlar(geom):
    """Yalnız alan geometrilerini tut (kırpma sonrası çizgi/nokta artıkları atılır)."""
    if geom.is_empty:
        return geom
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else geom.__class__()


class Toplayici(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.fab = osmium.geom.GeoJSONFactory()
        self.il, self.ilce = [], []
        self.hatali = []
        self.eski = []

    def area(self, a):
        t = a.tags
        if t.get("boundary") != "administrative" or a.from_way():
            return
        lvl = t.get("admin_level")
        if lvl not in ("4", "6"):
            return
        # kullanımdan kalkmış / tarihî kayıtlar
        if any(k.k.startswith(("disused:", "was:", "abandoned:", "old_boundary")) for k in t) or "end_date" in t:
            self.eski.append({"osm_id": a.orig_id(), "ad": t.get("name", "")})
            return
        try:
            g = shape(json.loads(self.fab.create_multipolygon(a)))
        except Exception as e:  # kırık ilişki (eksik üye)
            self.hatali.append({"osm_id": a.orig_id(), "ad": t.get("name", ""), "hata": str(e)[:120]})
            return
        if not g.is_valid:
            g = poligonlar(make_valid(g))
        kayit = {
            "osm_id": a.orig_id(),
            "ad": RESMI_AD.get(a.orig_id()) or t.get("name:tr") or t.get("name") or "",
            "osm_ad": t.get("name:tr") or t.get("name") or "",
            "wikidata": t.get("wikidata", ""),
            "iso": t.get("ISO3166-2", ""),
            "etiket_sayisi": len(t),
            "geom": g,
        }
        (self.il if lvl == "4" else self.ilce).append(kayit)


def kara_yukle(yol):
    """Kara poligonlarını Türkiye kapsamıyla sınırlı olarak oku (pyshp, saf Python)."""
    import shapefile  # pyshp
    r = shapefile.Reader(yol)
    parcalar = []
    kutu = box(*TR_BBOX)
    for s in r.iterShapes():
        if s.bbox[2] < TR_BBOX[0] or s.bbox[0] > TR_BBOX[2] or s.bbox[3] < TR_BBOX[1] or s.bbox[1] > TR_BBOX[3]:
            continue
        g = shape(s.__geo_interface__)
        if not g.is_valid:
            g = make_valid(g)
        if g.intersects(kutu):
            parcalar.append(g)
    return parcalar


def kirp(geom, agac, parcalar):
    adaylar = [parcalar[i] for i in agac.query(geom)]
    if not adaylar:
        return geom.__class__()
    return poligonlar(geom.intersection(unary_union(adaylar)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osm")
    ap.add_argument("cikti")
    ap.add_argument("--kara", help="land-polygons-split-4326/land_polygons.shp")
    ap.add_argument("--tarih", help="veri tarihi (YYYY-MM-DD); verilmezse dosya başlığından")
    a = ap.parse_args()
    os.makedirs(a.cikti, exist_ok=True)

    tarih = a.tarih
    if not tarih:
        try:
            h = osmium.io.Reader(a.osm, osmium.osm.osm_entity_bits.NOTHING).header()
            ts = h.get("osmosis_replication_timestamp", "")
            tarih = ts[:10] if ts else ""
        except Exception:
            tarih = ""

    t = Toplayici()
    idx = "flex_mem"
    t.apply_file(a.osm, locations=True, idx=idx)

    # --- İller: yalnız TR-NN ---
    iller = []
    for k in t.il:
        m = ISO_RE.match(k["iso"])
        if m:
            k["il_kodu"] = m.group(1)
            iller.append(k)
    iller.sort(key=lambda k: k["il_kodu"])
    kodlar = [k["il_kodu"] for k in iller]
    yinelenen = sorted({c for c in kodlar if kodlar.count(c) > 1})
    if yinelenen:
        sys.exit("Aynı plaka koduyla birden çok il: " + ", ".join(yinelenen))

    il_agac = STRtree([k["geom"] for k in iller])

    # --- İlçeler: temsil noktası bir ilin içinde ---
    ilceler, disarida = [], 0
    for k in t.ilce:
        p = k["geom"].representative_point()
        ev = None
        for i in il_agac.query(p):
            if iller[i]["geom"].contains(p):
                ev = iller[i]
                break
        if ev is None:
            disarida += 1
            continue
        k["il_kodu"], k["il_adi"] = ev["il_kodu"], ev["ad"]
        ilceler.append(k)

    # --- Denizden kırpma ---
    kirpildi = False
    if a.kara:
        parcalar = kara_yukle(a.kara)
        agac = STRtree(parcalar)
        for k in iller + ilceler:
            k["geom"] = kirp(k["geom"], agac, parcalar)
        kirpildi = True

    # --- İlçe çakışmaları: mükerrer/eski kayıtları ayıkla, kısmi çakışmaları raporla ---
    # Aynı ildeki iki ilçe kesişiyorsa kesişim alanı küçük olanın alanına oranlanır.
    #  >= %90 : küçük olan, büyüğün içinde kalan mükerrer ya da eski bir ilişkidir; çıkarılır.
    #  >  0,5 km² ya da > %1 : kısmi çakışma; yayın durdurulur (yayinla.mjs).
    cikarilan, cakisma = [], []
    ag = STRtree([k["geom"] for k in ilceler])
    sil = set()
    for i, k in enumerate(ilceler):
        if i in sil or k["geom"].is_empty:
            continue
        for j in ag.query(k["geom"]):
            j = int(j)
            if j <= i or j in sil or ilceler[j]["il_kodu"] != k["il_kodu"]:
                continue
            m = ilceler[j]
            kes = k["geom"].intersection(m["geom"])
            if kes.is_empty or kes.area == 0:
                continue
            kes = poligonlar(kes)
            if kes.is_empty:
                continue
            kucuk, buyuk, ki, bi = (k, m, i, j) if k["geom"].area <= m["geom"].area else (m, k, j, i)
            oran = kes.area / kucuk["geom"].area
            kes_km2 = jeodezik_alan_km2(kes)
            if oran >= 0.9:
                # Neredeyse aynı büyüklükteyse (eşdeğer kayıtlar) hangisinin güncel olduğuna etiketlerle karar ver:
                # Wikidata bağlantısı olan, sonra etiketi çok olan tutulur; karar verilemezse çakışma sayılır.
                ayni = kucuk["geom"].area / buyuk["geom"].area > 0.95
                if ayni:
                    pk = (bool(kucuk["wikidata"]), kucuk["etiket_sayisi"]); pb = (bool(buyuk["wikidata"]), buyuk["etiket_sayisi"])
                    if pk == pb:
                        cakisma.append({"il_kodu": k["il_kodu"], "ilce_1": k["ad"], "ilce_2": m["ad"], "kesisim_km2": round(kes_km2, 3), "oran": round(oran, 4), "not": "eşdeğer iki kayıt; hangisinin güncel olduğu belirlenemedi"})
                        continue
                    if pk > pb:  # küçük görünen daha güvenilir: büyüğü çıkar
                        kucuk, buyuk, ki, bi = buyuk, kucuk, bi, ki
                sil.add(ki)
                cikarilan.append({"il_kodu": k["il_kodu"], "ilce": kucuk["ad"], "osm_id": kucuk["osm_id"], "icinde_kaldigi": buyuk["ad"], "icinde_kaldigi_osm_id": buyuk["osm_id"], "oran": round(oran, 4)})
            elif kes_km2 > 0.5 or oran > 0.01:
                cakisma.append({"il_kodu": k["il_kodu"], "ilce_1": k["ad"], "ilce_2": m["ad"], "kesisim_km2": round(kes_km2, 3), "oran": round(oran, 4)})
    ilceler = [k for i, k in enumerate(ilceler) if i not in sil]

    # --- Alanlar ve denetim ---
    for k in iller + ilceler:
        k["alan_km2"] = round(jeodezik_alan_km2(k["geom"]), 3) if not k["geom"].is_empty else 0.0
    bos = [k["ad"] for k in ilceler if k["geom"].is_empty]
    ilceler = [k for k in ilceler if not k["geom"].is_empty]
    ilceler.sort(key=lambda k: (k["il_kodu"], k["ad"]))
    kimlikler = {k["osm_id"] for k in ilceler}
    for oid, ad in RESMI_AD.items():
        if oid not in kimlikler:
            print("UYARI: resmî ad eşlemesi boşa düştü (OSM kimliği yok):", oid, ad, file=sys.stderr)

    kapsama = []
    for il in iller:
        toplam = sum(k["alan_km2"] for k in ilceler if k["il_kodu"] == il["il_kodu"])
        oran = toplam / il["alan_km2"] if il["alan_km2"] else 0
        il["ilce_sayisi"] = sum(1 for k in ilceler if k["il_kodu"] == il["il_kodu"])
        if abs(oran - 1) > 0.005:
            kapsama.append({"il_kodu": il["il_kodu"], "il_adi": il["ad"], "ilce_toplam_km2": round(toplam, 3), "il_km2": il["alan_km2"], "oran": round(oran, 5)})

    def yaz(ad, kayitlar, alanlar):
        fc = {"type": "FeatureCollection", "features": []}
        for k in kayitlar:
            fc["features"].append({"type": "Feature", "properties": {f: k.get(src) for f, src in alanlar}, "geometry": mapping(k["geom"])})
        with open(os.path.join(a.cikti, ad), "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))

    yaz("il-ham.geojson", iller, [("il_kodu", "il_kodu"), ("il_adi", "ad"), ("ilce_sayisi", "ilce_sayisi"), ("alan_km2", "alan_km2"), ("wikidata", "wikidata"), ("osm_id", "osm_id")])
    yaz("ilce-ham.geojson", ilceler, [("il_kodu", "il_kodu"), ("il_adi", "il_adi"), ("ilce_adi", "ad"), ("alan_km2", "alan_km2"), ("wikidata", "wikidata"), ("osm_id", "osm_id")])

    rapor = {
        "veri_tarihi": tarih,
        "derleme_zamani": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "il_sayisi": len(iller), "ilce_sayisi": len(ilceler),
        "il_disinda_kalan_ilce": disarida, "bos_kalan_ilce": bos,
        "kirik_iliski": t.hatali[:50], "kirik_iliski_sayisi": len(t.hatali),
        "kiyidan_kirpildi": kirpildi, "kapsama_uyumsuz": kapsama,
        "cikarilan_mukerrer_ilce": cikarilan, "ilce_cakismasi": cakisma, "eski_kayit_suzuldu": t.eski[:50],
        "kaynak": "© OpenStreetMap katkıcıları, ODbL 1.0",
    }
    with open(os.path.join(a.cikti, "derleme.json"), "w", encoding="utf-8") as f:
        json.dump(rapor, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: rapor[k] for k in ("veri_tarihi", "il_sayisi", "ilce_sayisi", "il_disinda_kalan_ilce", "kirik_iliski_sayisi", "kiyidan_kirpildi")}, ensure_ascii=False))
    print("Kapsama uyumsuz il:", len(kapsama))
    for c in cikarilan:
        print("Mükerrer ilçe çıkarıldı:", c["il_kodu"], c["ilce"], "osm", c["osm_id"], "→", c["icinde_kaldigi"], "içinde (%{:.1f})".format(c["oran"] * 100))
    for c in cakisma:
        print("İlçe çakışması:", c["il_kodu"], c["ilce_1"], "/", c["ilce_2"], c["kesisim_km2"], "km²")


if __name__ == "__main__":
    main()
