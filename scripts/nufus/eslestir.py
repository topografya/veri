# TÜİK ilçe adlarını OSM ilçe sınırlarıyla (ozet.json) eşleştirir; eşleşmeyenleri raporlar
import csv,glob,json,unicodedata,re,sys
import os; R=os.path.join(os.path.dirname(__file__), 'ham') + '/'
oz=json.load(open(os.environ.get('SINIR_OZET', os.path.join(os.path.dirname(__file__), '..', '..', 'sinirlar', 'ozet.json'))))
def norm(s):
    s=s.replace('İ','i').replace('I','ı').lower()
    s=unicodedata.normalize('NFKD',s); s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-zçğıöşü0-9]','',s.replace('ı','i'))
t22=list(csv.reader(open(glob.glob(R+'*T221*')[0],encoding='utf-8-sig'),delimiter=';'))[1:]
s=[x[4] for x in t22 if x[5]=='2025' and x[3]=='Toplam'][1:]
iladi={norm(i['ad']):i for i in oz['iller']}
cur=None; tuik={}
for n in s:
    if norm(n) in iladi and (cur is None or norm(n)!=norm(cur) ) and n not in sum(tuik.values(),[]):
        if norm(n) in iladi and not any(n==x for v in tuik.values() for x in v): cur=n; tuik[cur]=[]; continue
    tuik[cur].append(n)
print('il',len(tuik),'ilçe',sum(len(v) for v in tuik.values()))
eksik=[]; fazla=[]
for il,ilceler in tuik.items():
    o=iladi[norm(il)]; osm={norm(c['ad']):c['ad'] for c in o['ilceler']}
    def key(n):
        k=norm(n)
        if k in osm: return k
        k2=norm(n[len(il):]) if norm(n).startswith(norm(il)) else None   # "Ankara Gölbaşı" → Gölbaşı
        if k2 and k2 in osm: return k2
        return None
    used=set()
    for n in ilceler:
        k=key(n)
        if k: used.add(k)
        else: eksik.append((il,n))
    for k,v in osm.items():
        if k not in used: fazla.append((il,v))
print('TÜİK var OSM yok:',len(eksik),eksik[:40]); print('OSM var TÜİK yok:',len(fazla),fazla[:40])
