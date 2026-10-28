#!/usr/bin/env python3
"""
Mahalle ve köy verisinin yayın öncesi denetimi. Bir eşik aşılırsa sıfırdan farklı kodla biter ve yayın yapılmaz.

Denetimler:
  1. Bütünlük: her ilçe için bir dosya; birim sayısı ve nüfus toplamı TÜİK ham dosyalarıyla birebir aynı.
  2. Öznitelikler: kod, ad, tür, nüfus ve gösterim türü (s/n/-) geçerli; geometri türü gösterimle uyumlu.
  3. Geometri: sınırlar geçerli çokgen, temsil noktası çokgenin içinde, noktalar Türkiye kutusunda.
  4. Bindirme: aynı ilçede sınırlar birbirine küçük olanın %5'inden fazla binmez (uret.py bunları noktaya çevirir).
  5. Kapsam: nüfusun en az %90'ı konumlu (sınır ya da nokta), en az %60'ı sınırlı birimlerde; önceki yayına göre
     sınırlı birim sayısı %5'ten, konumlu nüfus payı 2 puandan fazla düşmez.
Bilinen istisnalar izin listesine (izin.json: {"bindirme": [[tuik_kod_a, tuik_kod_b], ...]}) yazılarak geçilebilir.

Kullanım: denetle.py <mahalle klasörü> <sinirlar/ozet.json> <medas_mahalle.csv> <medas_koy.csv> [önceki mahalle/ozet.json]
"""
import csv, json, os, sys, collections
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
sys.path.insert(0, os.path.dirname(__file__))
import kapsam  # noqa: E402  (tuik_oku)

TR_KUTU = (25.5, 35.7, 45.0, 42.3)
hatalar, uyarilar = [], []


def hata(m):
    hatalar.append(m)


def main():
    kok, sinir_ozet, mah_csv, koy_csv = sys.argv[1:5]
    onceki = sys.argv[5] if len(sys.argv) > 5 and os.path.exists(sys.argv[5]) else None
    izin = {"bindirme": []}
    izin_yol = os.path.join(os.path.dirname(__file__), "izin.json")
    if os.path.exists(izin_yol):
        izin = json.load(open(izin_yol, encoding="utf-8"))
    izinli = {tuple(sorted(map(int, x))) for x in izin.get("bindirme", [])}

    ozet = json.load(open(os.path.join(kok, "ozet.json"), encoding="utf-8"))
    sinir = json.load(open(sinir_ozet, encoding="utf-8"))
    beklenen_ilce = {str(c["osm_id"]) for i in sinir["iller"] for c in i["ilceler"]}

    # TÜİK ham toplamları (kapsam.py ile aynı dosyalar): kod → nüfus
    # TÜİK ham dosyaları (kapsam.py ile aynı okuyucu): kod → nüfus
    tuik = {(x["tur"][0], x["kod"]): x["nufus"] for yol, tur in ((mah_csv, "mahalle"), (koy_csv, "koy")) for x in kapsam.tuik_oku(yol, tur)}
    if not tuik:
        hata("TÜİK dosyaları okunamadı")

    gorulen_ilce, kodlar, n_top = set(), {}, 0
    say = collections.Counter(); nuf = collections.Counter()
    for il in ozet["iller"]:
        for c in il["ilceler"]:
            osm = str(c["osm_id"]); gorulen_ilce.add(osm)
            yol = os.path.join(kok, il["kod"], osm + ".geojson")
            if not os.path.exists(yol):
                hata("ilçe dosyası yok: " + yol); continue
            fs = json.load(open(yol, encoding="utf-8"))["features"]
            poligonlar = []
            for f in fs:
                p, g = f["properties"], f["geometry"]
                ad = "%s/%s %s" % (il["ad"], c["ad"], p.get("a"))
                if not isinstance(p.get("k"), int) or not p.get("a") or p.get("t") not in ("m", "k") or not isinstance(p.get("n"), int) or p["n"] < 0:
                    hata("geçersiz öznitelik: " + ad); continue
                anahtar = ("m" if p["t"] == "m" else "k", p["k"])  # TÜİK kodları mahalle ve köy listelerinde ayrı numaralanır
                if anahtar in kodlar:
                    hata("yinelenen TÜİK kodu %s: %s" % (anahtar, ad))
                kodlar[anahtar] = p["n"]; n_top += p["n"]; say[p["g"]] += 1; nuf[p["g"]] += p["n"]
                if p["g"] == "-":
                    if g is not None: hata("geometrisiz işaretli ama geometri var: " + ad)
                    continue
                if g is None:
                    hata("geometri eksik: " + ad); continue
                sh = shape(g)
                if p["g"] == "s":
                    if sh.geom_type not in ("Polygon", "MultiPolygon") or sh.is_empty:
                        hata("sınır çokgen değil: " + ad); continue
                    if not sh.is_valid:
                        hata("geçersiz çokgen: " + ad)
                    if "c" not in p or not sh.buffer(1e-6).contains(Point(p["c"])):
                        hata("temsil noktası çokgenin dışında: " + ad)
                    poligonlar.append((sh, p))
                elif p["g"] == "n":
                    if sh.geom_type != "Point":
                        hata("nokta işaretli ama geometri %s: %s" % (sh.geom_type, ad)); continue
                    if not (TR_KUTU[0] <= sh.x <= TR_KUTU[2] and TR_KUTU[1] <= sh.y <= TR_KUTU[3]):
                        hata("nokta Türkiye dışında: " + ad)
                else:
                    hata("bilinmeyen gösterim türü %r: %s" % (p["g"], ad))
            # Bindirme
            if poligonlar:
                gs = [x[0] for x in poligonlar]; agac = STRtree(gs)
                for i, gi in enumerate(gs):
                    for j in agac.query(gi):
                        if j <= i: continue
                        kucuk = min(gi.area, gs[j].area)
                        if kucuk > 0 and gi.intersection(gs[j]).area / kucuk > 0.05:
                            cift = tuple(sorted((poligonlar[i][1]["k"], poligonlar[j][1]["k"])))
                            (uyarilar if cift in izinli else hatalar).append("bindiren sınırlar: %s/%s %s – %s" % (il["ad"], c["ad"], poligonlar[i][1]["a"], poligonlar[j][1]["a"]))

    # Bütünlük
    if gorulen_ilce != beklenen_ilce:
        hata("ilçe kümesi sınır verisinden farklı: eksik %d, fazla %d" % (len(beklenen_ilce - gorulen_ilce), len(gorulen_ilce - beklenen_ilce)))
    if set(kodlar) != set(tuik):
        hata("birim kümesi TÜİK'ten farklı: eksik %d, fazla %d" % (len(set(tuik) - set(kodlar)), len(set(kodlar) - set(tuik))))
    yanlis = [k for k in kodlar if k in tuik and kodlar[k] != tuik[k]]
    if yanlis:
        hata("%d birimde nüfus TÜİK'ten farklı (ör. %s)" % (len(yanlis), yanlis[0]))
    if n_top != sum(tuik.values()):
        hata("nüfus toplamı %d, TÜİK %d" % (n_top, sum(tuik.values())))

    # Kapsam
    konumlu = (nuf["s"] + nuf["n"]) / n_top if n_top else 0
    sinirli = nuf["s"] / n_top if n_top else 0
    if konumlu < 0.90: hata("konumlu nüfus payı %%%.1f (< %%90)" % (100 * konumlu))
    if sinirli < 0.60: hata("sınırlı nüfus payı %%%.1f (< %%60)" % (100 * sinirli))
    if onceki:
        o = json.load(open(onceki, encoding="utf-8"))
        oc = [c for i in o["iller"] for c in i["ilceler"]]
        o_sinir = sum(c["sinir"] for c in oc)
        o_konumlu = sum(c["nufus"] for c in oc)  # yalnız toplam vardır; birim payıyla karşılaştırılır
        o_birim = sum(c["birim"] for c in oc); o_yok = sum(c["yok"] for c in oc)
        if o_sinir and say["s"] < 0.95 * o_sinir:
            hata("sınırlı birim sayısı önceki yayına göre %%5'ten fazla düştü: %d → %d" % (o_sinir, say["s"]))
        if o_birim and (1 - say["-"] / sum(say.values())) < (1 - o_yok / o_birim) - 0.02:
            hata("konumlu birim payı önceki yayına göre 2 puandan fazla düştü")

    print("Mahalle denetimi: %d ilçe, %d birim, nüfus %d; sınır %d, nokta %d, yok %d; konumlu nüfus %%%.1f, sınırlı %%%.1f"
          % (len(gorulen_ilce), sum(say.values()), n_top, say["s"], say["n"], say["-"], 100 * konumlu, 100 * sinirli))
    for u in uyarilar: print("UYARI (izinli):", u)
    if hatalar:
        for h in hatalar[:50]: print("HATA:", h, file=sys.stderr)
        sys.exit("Mahalle denetimi başarısız: %d hata" % len(hatalar))
    print("Mahalle denetimi geçti.")


if __name__ == "__main__":
    main()
