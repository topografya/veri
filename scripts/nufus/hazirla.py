# TÜİK ADNKS toplu veri setlerinden (CSV) Nüfus ve Demografi Haritası verisini üretir.
# Girdi: ham/*.csv (veriportali.tuik.gov.tr → Toplu Veri Seti İndirme, CSV)
# Çıktı: /home/claude/veri/nufus/{gostergeler.json, piramit.json}
# Kullanım: python3 hazirla.py
import csv, glob, json, os, re, unicodedata, sys, datetime

HAM = os.environ.get('NUFUS_HAM', os.path.join(os.path.dirname(__file__), 'ham'))
CIKTI = os.environ.get('NUFUS_CIKTI', os.path.join(os.path.dirname(__file__), '..', '..', 'nufus'))
OZET = os.environ.get('SINIR_OZET', os.path.join(os.path.dirname(__file__), '..', '..', 'sinirlar', 'ozet.json'))
YAS = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70-74', '75-79', '80-84', '85-89', '90+']

# OSM ilçe adı TÜİK adından farklı olanlar (OSM'de yazım hatası ya da "Merkez" ekinin olmaması). Anahtar: (il, TÜİK adı) → OSM adı
ELLE = {
    ('Çanakkale', 'Çanakkale Merkez'): 'Çanakkale', ('Uşak', 'Uşak Merkez'): 'Uşak', ('Kırıkkale', 'Balışeyh'): 'Balışıh',
    ('Yozgat', 'Sarıkaya'): 'Sarıkaya Deresi', ('Amasya', 'Amasya Merkez'): 'Amasya', ('Tokat', 'Tokat Merkez'): 'Tokat',
    ('Ağrı', 'Patnos'): 'Panos', ('Iğdır', 'Iğdır Merkez'): 'Iğdır', ('Tunceli', 'Nazımiye'): 'Nazmiye', ('Siirt', 'Siirt Merkez'): 'Siirt',
}

def norm(s):
    s = s.replace('İ', 'i').replace('I', 'ı').lower()
    s = unicodedata.normalize('NFKD', s); s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9ı]', '', s).replace('ı', 'i')

def oku(kod):
    f = [x for x in glob.glob(os.path.join(HAM, '*.csv')) if re.search(r'TRDF_ADNKS_' + kod + r'\d\.\d\.csv$', x)]
    if len(f) != 1: sys.exit('Dosya bulunamadı ya da birden çok: ' + kod)
    r = list(csv.reader(open(f[0], encoding='utf-8-sig'), delimiter=';'))
    h = [re.sub(r'\s*\(.*\)$', '', c) for c in r[0]]
    return [dict(zip(h, x)) for x in r[1:]], os.path.basename(f[0])

def sayi(s):
    if s == '' or s is None: return None
    return float(s.replace(',', '.'))

oz = json.load(open(OZET))
iller = oz['iller']; IL = {norm(i['ad']): i for i in iller}

# --- T16: il, yaş grubu, cinsiyet (2007–2025) → nüfus serisi ve piramit
t16, f16 = oku('T16')
yillar = sorted({int(x['Zaman']) for x in t16})
Y = {y: i for i, y in enumerate(yillar)}
def yer_kod(ad):
    if ad in ('Toplam', 'Türkiye'): return 'TR'
    i = IL.get(norm(ad));
    if not i: sys.exit('İl eşleşmedi: ' + ad)
    return i['kod']
nufus = {}; piramit = {}
for x in t16:
    k = yer_kod(x['İkamet edilen yer']); y = Y[int(x['Zaman'])]; v = int(x['Gözlem'])
    if x['Cinsiyet'] == 'Toplam' and x['Yaş Grubu'] == 'Toplam':
        nufus.setdefault(k, [None] * len(yillar))[y] = v
    elif x['Cinsiyet'] in ('Erkek', 'Kadın') and x['Yaş Grubu'] != 'Toplam':
        p = piramit.setdefault(k, {'E': [[0] * len(YAS) for _ in yillar], 'K': [[0] * len(YAS) for _ in yillar]})
        p['E' if x['Cinsiyet'] == 'Erkek' else 'K'][y][YAS.index(x['Yaş Grubu'])] = v
# piramit tutarlılık: E+K yaş grupları toplamı = nüfus
for k, p in piramit.items():
    for y in range(len(yillar)):
        s = sum(p['E'][y]) + sum(p['K'][y])
        if s != nufus[k][y]: sys.exit('Piramit toplamı tutmuyor: %s %d %d≠%d' % (k, yillar[y], s, nufus[k][y]))

def seri(rows, filt, yer_alan='İkamet edilen yer', dec=2):
    out = {}
    for x in rows:
        if not filt(x): continue
        k = yer_kod(x[yer_alan]); y = int(x['Zaman'])
        if y not in Y: continue
        v = sayi(x['Gözlem']); out.setdefault(k, [None] * len(yillar))[Y[y]] = None if v is None else round(v, dec)
    return out

t23, f23 = oku('T23'); t24, f24 = oku('T24'); t25, f25 = oku('T25')
ortanca = {c: seri(t23, lambda x, c=c: x['Cinsiyet'] == c, dec=1) for c in ('Toplam', 'Erkek', 'Kadın')}
bag = {k: seri(t24, lambda x, g=g: x['ADNKS Gösterge'].startswith(g), dec=1) for k, g in (('toplam', 'Toplam yaş'), ('cocuk', 'Çocuk'), ('yasli', 'Yaşlı'))}
hh = seri(t25, lambda x: True, dec=2)

# --- T22 + T38: ilçe nüfusu (2024, 2025), merkez/köy, artış hızı
t22, f22 = oku('T22'); t38, f38 = oku('T38')
sira = []; [sira.append(x['İkamet edilen yer']) for x in t22 if x['İkamet edilen yer'] not in sira]
il_of = {}; cur = None
for ad in sira[1:]:
    if norm(ad) in IL and ad not in il_of: cur = ad; il_of[ad] = None; continue
    il_of[ad] = cur
d22 = {}
for x in t22:
    d22.setdefault(x['İkamet edilen yer'], {})[(x['Yerleşim Yeri türü'], x['Zaman'])] = int(x['Gözlem'])
# TÜİK, değeri olmayan satırları (ör. köyü bulunmayan büyükşehir ilçeleri) dosyaya koymaz → 0; toplamla ayrıca denetlenir
def gk(g, tur, yil):
    v = g.get((tur, yil))
    if v is None:
        v = 0 if tur != 'Toplam' else None
    return v
for ad, g in d22.items():
    for yil in ('2024', '2025'):
        if gk(g, 'İl ve ilçe merkezleri', yil) + gk(g, 'Belde ve köyler', yil) != g[('Toplam', yil)]: sys.exit('Merkez + köy ≠ toplam: ' + ad)
d38 = {}
for x in t38: d38.setdefault(x['İkamet edilen yer'], {})[x['Zaman']] = sayi(x['Gözlem'])

cikti_iller = []; eslesmeyen = []
for il in iller:
    o = {'kod': il['kod'], 'ad': il['ad'], 'alan_km2': il['alan_km2'], 'ilceler': []}
    tad = next(a for a in sira if norm(a) == norm(il['ad']))
    osm = {norm(c['ad']): c for c in il['ilceler']}
    for ad in [a for a, p in il_of.items() if p == tad]:
        c = None
        if (tad, ad) in ELLE: c = osm.get(norm(ELLE[(tad, ad)]))
        if not c: c = osm.get(norm(ad))
        if not c and norm(ad).startswith(norm(tad)): c = osm.get(norm(ad)[len(norm(tad)):])
        if not c: eslesmeyen.append((tad, ad)); continue
        g = d22[ad]
        o['ilceler'].append({'ad': ad, 'osm_id': c['osm_id'], 'alan_km2': c['alan_km2'],
            'n': [g[('Toplam', '2024')], g[('Toplam', '2025')]], 'merkez': [gk(g, 'İl ve ilçe merkezleri', '2024'), gk(g, 'İl ve ilçe merkezleri', '2025')],
            'koy': [gk(g, 'Belde ve köyler', '2024'), gk(g, 'Belde ve köyler', '2025')],
            'artis': [round(d38[ad]['2024'], 2), round(d38[ad]['2025'], 2)]})
    s = sum(c['n'][1] for c in o['ilceler'])
    if s != nufus[il['kod']][Y[2025]]: sys.exit('İlçe toplamı il nüfusunu tutmuyor: %s %d≠%d' % (il['ad'], s, nufus[il['kod']][Y[2025]]))
    if len(o['ilceler']) != len(il['ilceler']): sys.exit('İlçe sayısı farklı: %s TÜİK %d, OSM %d' % (il['ad'], len(o['ilceler']), len(il['ilceler'])))
    g = d22[tad]; o['merkez'] = [gk(g, 'İl ve ilçe merkezleri', '2024'), gk(g, 'İl ve ilçe merkezleri', '2025')]; o['koy'] = [gk(g, 'Belde ve köyler', '2024'), gk(g, 'Belde ve köyler', '2025')]
    o['artis_ilce_tablosu'] = [round(d38[tad]['2024'], 2), round(d38[tad]['2025'], 2)]
    cikti_iller.append(o)
if eslesmeyen: sys.exit('Eşleşmeyen ilçeler: %r' % eslesmeyen)

# Piramitten türetilen oranlar (%): 0–14, 15–64, 65+ ve cinsiyet oranı (100 kadına düşen erkek)
def turet(k):
    p = piramit[k]; o = {'yas014': [], 'yas65': [], 'cins_orani': []}
    for y in range(len(yillar)):
        t = [p['E'][y][i] + p['K'][y][i] for i in range(len(YAS))]; n = sum(t)
        o['yas014'].append(round(100 * sum(t[:3]) / n, 2)); o['yas65'].append(round(100 * sum(t[13:]) / n, 2))
        o['cins_orani'].append(round(100 * sum(p['E'][y]) / sum(p['K'][y]), 1))
    return o
# Yıllık nüfus artış hızı (‰) = ln(P_t / P_t-1) × 1000 (TÜİK tanımı); T38'deki il değerleriyle denetlenir
import math
def artis(k):
    n = nufus[k]; return [None] + [round(1000 * math.log(n[i] / n[i - 1]), 2) for i in range(1, len(n))]
def ilseri(k):
    return dict(turet(k), artis=artis(k), **{'nufus': nufus[k], 'ortanca': [ortanca['Toplam'].get(k), ortanca['Erkek'].get(k), ortanca['Kadın'].get(k)],
            'bagimlilik': [bag['toplam'].get(k), bag['cocuk'].get(k), bag['yasli'].get(k)], 'hanehalki': hh.get(k)})
for o in cikti_iller: o.update(ilseri(o['kod']))
for o in cikti_iller:
    a = artis(o['kod'])
    # 2024–2025 için TÜİK'in yayımladığı değer (T38) esastır: sınır/yerleşim değişikliği olan illerde TÜİK karşılaştırılabilir
    # nüfusla hesaplar (ör. 2025 Giresun, Gümüşhane); ham nüfustan hesaplanan değer o yıllarda farklı çıkar
    for j, yil in enumerate((2024, 2025)):
        if abs(a[Y[yil]] - o['artis_ilce_tablosu'][j]) > 0.02: print('Not: %s %d artış hızı ham %.2f, TÜİK %.2f (TÜİK değeri kullanıldı)' % (o['ad'], yil, a[Y[yil]], o['artis_ilce_tablosu'][j]))
        o['artis'][Y[yil]] = o['artis_ilce_tablosu'][j]
    del o['artis_ilce_tablosu']
g = d22['Toplam']
tr = dict(ilseri('TR'), merkez=[g[('İl ve ilçe merkezleri', '2024')], g[('İl ve ilçe merkezleri', '2025')]], koy=[g[('Belde ve köyler', '2024')], g[('Belde ve köyler', '2025')]],
          alan_km2=round(sum(i['alan_km2'] for i in iller), 3))
# --- T17: Türkiye nüfus yoğunluğu (TÜİK yayını; göl yüzeyleri hariç yüzölçümüyle). İl/ilçede TÜİK yoğunluk tablosu
# toplu indirmede yok; orada OSM sınır alanı kullanılır (göl ve iç sular dahil, değer TÜİK'ten birkaç % düşük çıkabilir).
t17, f17 = oku('T17')
yog = {int(x['Zaman']): sayi(x['Gözlem']) for x in t17 if x['ADNKS Gösterge'] == 'Nüfus yoğunluğu'}
tr['yogunluk_tuik'] = [round(yog[y], 2) if y in yog else None for y in yillar]
if abs(tr['yogunluk_tuik'][-1] - 111.96) > 0.01: sys.exit('T17 yoğunluk beklenmedik: %r' % tr['yogunluk_tuik'][-1])

# --- T21: medeni durum (yalnız Türkiye)
t21, f21 = oku('T21'); medeni = {}
for x in t21:
    if int(x['Zaman']) != yillar[-1]: continue
    medeni.setdefault(x['Cinsiyet'], {})[x['Medeni Durum']] = int(x['Gözlem'])
tr['medeni'] = {'yil': yillar[-1], 'deger': medeni}

kaynak = {'kurum': 'Türkiye İstatistik Kurumu (TÜİK)', 'urun': 'Adrese Dayalı Nüfus Kayıt Sistemi (ADNKS) Sonuçları', 'portal': 'https://veriportali.tuik.gov.tr/tr/bulk-download',
          'tablolar': {'T16': f16, 'T21': f21, 'T22': f22, 'T23': f23, 'T24': f24, 'T25': f25, 'T38': f38, 'T17': f17},
          'kosul': 'TÜİK verileri kaynak gösterilerek izin gerekmeksizin yeniden kullanılabilir (tuik.gov.tr Yasal Uyarı).',
          'sinir': 'İl ve ilçe sınırları ve alanları: © OpenStreetMap katkıcıları, ODbL 1.0 (topografya/veri). Resmî sınır değildir.',
          'artis_notu': 'Yıllık nüfus artış hızı (‰) = ln(Pt/Pt-1) × 1000. 2024 ve 2025 için TÜİK tablosu (T38) esas alınmıştır; 2008–2023 değerleri il nüfuslarından aynı formülle hesaplanmıştır, sınır değişikliği olan yıllarda TÜİK değerlerinden farklı olabilir.',
          'alan_notu': 'Türkiye yoğunluğu TÜİK\'in yayımladığı değerdir (T17; göl yüzeyleri hariç). İl ve ilçe yoğunluğu nüfusun OSM sınır alanına bölünmesiyle bulunur; bu alan göl ve iç suları içerdiğinden değer TÜİK\'in il yoğunluğundan birkaç % düşük çıkabilir.'}
os.makedirs(CIKTI, exist_ok=True)
out = {'surum': 1, 'derleme': datetime.date.today().isoformat(), 'kaynak': kaynak, 'yillar': yillar, 'ilce_yillari': [2024, 2025], 'yas_gruplari': YAS, 'tr': tr, 'iller': cikti_iller}
json.dump(out, open(os.path.join(CIKTI, 'gostergeler.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump({'yillar': yillar, 'yas_gruplari': YAS, 'piramit': piramit}, open(os.path.join(CIKTI, 'piramit.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
print('Tamam: %d il, %d ilçe, yıllar %d–%d' % (len(cikti_iller), sum(len(o['ilceler']) for o in cikti_iller), yillar[0], yillar[-1]))
for f in ('gostergeler.json', 'piramit.json'): print(f, os.path.getsize(os.path.join(CIKTI, f)) // 1024, 'KB')
