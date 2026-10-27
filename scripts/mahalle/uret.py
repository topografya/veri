#!/usr/bin/env python3
"""
Mahalle ve köy harita verisi: kapsam.py'nin eşleştirmesine (eslesme.csv) göre her il için bir GeoJSON üretir.
Her TÜİK mahalle/köyü bir özelliktir:
  - OSM'de sınırı varsa çokgen (ilçe sınırıyla kırpılır, ~5 m sadeleştirilir),
  - yalnız noktası varsa nokta,
  - ikisi de yoksa geometrisi boş (null) — tabloda yine görünür.
Özellikler: k (TÜİK kodu), a (ad), t (m: mahalle, k: köy), b (belediye), i (ilçe), n (2025 nüfusu), g (s: sınır, n: nokta, -: yok), o (OSM kimliği)
Kalite: aynı ilçedeki sınırların çakışması ve ilçe dışına taşan sınırlar kalite.json'a yazılır.

Kullanım: uret.py <yer.osm.pbf> <ilce-ham.geojson> <eslesme.csv> <osm_zaman.txt> <çıktı klasörü>
"""
import csv, json, os, sys, collections
from shapely.geometry import shape, mapping
from shapely.strtree import STRtree
from shapely.ops import unary_union
sys.path.insert(0, os.path.dirname(__file__))
import kapsam  # noqa: E402  (aynı klasör: norm, Toplayici)

SADE = 0.00005      # derece; ~5 m
HASSAS = 5          # ondalık basamak; ~1 m


def yuvarla(o):
    if isinstance(o, float):
        return round(o, HASSAS)
    if isinstance(o, (list, tuple)):
        return [yuvarla(x) for x in o]
    return o


def main():
    pbf, ilce_gj, esl_csv, zaman_txt, cikti = sys.argv[1:6]
    os.makedirs(os.path.join(cikti, "mahalle"), exist_ok=True)
    osm_tarih = open(zaman_txt).read().strip()[:10]

    ilceler = json.load(open(ilce_gj, encoding="utf-8"))["features"]
    ilce = {}
    il_kod = {}
    for f in ilceler:
        p = f["properties"]
        k = (kapsam.norm(p["il_adi"]), kapsam.norm(p["ilce_adi"]))
        ilce[k] = {"geom": shape(f["geometry"]), "il_kodu": p["il_kodu"], "il_adi": p["il_adi"], "ilce_adi": p["ilce_adi"]}
        il_kod[kapsam.norm(p["il_adi"])] = (p["il_kodu"], p["il_adi"])
    il_of = collections.defaultdict(set)
    for k in ilce:
        il_of[k[0]].add(k[1])

    def ilce_anahtar(il, ic):
        i, c = kapsam.norm(il), kapsam.norm(ic)
        for k in (c, i + "merkez" if c == "merkez" else None, i + c):
            if k and k in il_of[i]:
                return (i, k)
        return None

    t = kapsam.Toplayici()
    t.apply_file(pbf, locations=True, idx="flex_mem")
    geom_of = {o["osm"]: o["geom"] for o in t.ogeler}

    satirlar = list(csv.DictReader(open(esl_csv, encoding="utf-8")))
    il_ozellik = collections.defaultdict(list)
    ilce_poligon = collections.defaultdict(list)  # kalite denetimi için
    tasan = []
    for r in satirlar:
        k = ilce_anahtar(r["il"], r["ilce"])
        g, tip = None, "-"
        if k and r["osm"] and r["osm"] in geom_of:
            raw = geom_of[r["osm"]]
            if r["sonuc"].startswith("poligon"):
                ic = ilce[k]["geom"]
                kir = raw.intersection(ic) if not ic.contains(raw) else raw
                kir = kapsam_poligon(kir)
                if not kir.is_empty and raw.area > 0:
                    if kir.area / raw.area < 0.8:
                        tasan.append({"il": r["il"], "ilce": r["ilce"], "ad": r["ad"], "kod": r["tuik_kod"], "osm": r["osm"], "icerde_oran": round(kir.area / raw.area, 3)})
                    g, tip = kir.simplify(SADE, preserve_topology=True), "s"
                    ilce_poligon[k].append((g, r))
            else:
                g, tip = raw, "n"
        il_ad = k[0] if k else kapsam.norm(r["il"])
        kod, ad = il_kod.get(il_ad, ("??", r["il"]))
        il_ozellik[kod].append({"type": "Feature", "geometry": yuvarla(mapping(g)) if g is not None else None,
                                "properties": {"k": int(r["tuik_kod"]), "a": r["ad"], "t": "m" if r["tur"] == "mahalle" else "k", "b": r["belediye"],
                                               "i": r["ilce"], "n": int(r["nufus_2025"]), "g": tip, "o": r["osm"] or None}})

    # Kalite: aynı ilçede birbirine %5'ten fazla binen sınırlar
    cakisma = []
    for k, lst in ilce_poligon.items():
        gs = [x[0] for x in lst]
        agac = STRtree(gs)
        for i, gi in enumerate(gs):
            for j in agac.query(gi):
                if j <= i:
                    continue
                kes = gi.intersection(gs[j]).area
                kucuk = min(gi.area, gs[j].area)
                if kucuk > 0 and kes / kucuk > 0.05:
                    cakisma.append({"il": lst[i][1]["il"], "ilce": lst[i][1]["ilce"], "a": lst[i][1]["ad"], "b": lst[j][1]["ad"], "oran": round(kes / kucuk, 3)})

    ozet = {"surum": 1, "osm_tarihi": osm_tarih, "tuik": "TÜİK ADNKS 2025 (MEDAS, belediye/köy/mahalle nüfusları)",
            "kaynak": {"sinir_nokta": "© OpenStreetMap katkıcıları, ODbL 1.0", "nufus": "TÜİK, Adrese Dayalı Nüfus Kayıt Sistemi, 2025"},
            "iller": []}
    for kod in sorted(il_ozellik):
        fs = il_ozellik[kod]
        fs.sort(key=lambda f: (f["properties"]["i"], f["properties"]["a"]))
        yol = os.path.join(cikti, "mahalle", kod + ".geojson")
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": fs}, f, ensure_ascii=False, separators=(",", ":"))
        c = collections.Counter(x["properties"]["g"] for x in fs)
        ozet["iller"].append({"kod": kod, "ad": next((v[1] for v in il_kod.values() if v[0] == kod), kod), "birim": len(fs), "sinir": c["s"], "nokta": c["n"], "yok": c["-"],
                              "nufus": sum(x["properties"]["n"] for x in fs), "bayt": os.path.getsize(yol)})
    json.dump(ozet, open(os.path.join(cikti, "mahalle", "ozet.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    kalite = {"cakisan_sinir": sorted(cakisma, key=lambda x: -x["oran"]), "ilce_disina_tasan": sorted(tasan, key=lambda x: x["icerde_oran"])}
    json.dump(kalite, open(os.path.join(cikti, "kalite.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    top = sum(i["bayt"] for i in ozet["iller"])
    print("iller:", len(ozet["iller"]), "toplam boyut: %.1f MB" % (top / 1e6), "en büyük:", max(ozet["iller"], key=lambda i: i["bayt"])["ad"], max(i["bayt"] for i in ozet["iller"]))
    print("çakışan sınır çifti:", len(cakisma), "ilçe dışına taşan:", len(tasan))


def kapsam_poligon(g):
    """Kırpma sonrası yalnız alan geometrileri."""
    if g.is_empty or g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(parts) if parts else g.__class__()


if __name__ == "__main__":
    main()
