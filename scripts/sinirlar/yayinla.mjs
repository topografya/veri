#!/usr/bin/env node
/*
 * Türkiye il ve ilçe sınırları - yayın dosyaları (2. aşama)
 *
 * Girdi : <ham>/ilce-ham.geojson, <ham>/il-ham.geojson, <ham>/derleme.json (derle.py çıktısı)
 * Çıktı : <cikti>/ozet.json             il ve ilçe listesi, alanlar, kapsam kutuları, veri tarihi
 *         <cikti>/il.topo.json          iller, ayrıntılı (~30 m tolerans)
 *         <cikti>/il-sade.topo.json     iller, sade (~500 m)
 *         <cikti>/ilce-sade.topo.json   tüm ilçeler, sade (~500 m)
 *         <cikti>/ilce/NN.topo.json     her ilin ilçeleri, ayrıntılı (~30 m); NN plaka kodu
 *
 * Topoloji: Sadeleştirme ilçe katmanının ortak topolojisi üzerinde bir kez yapılır; komşu ilçeler arasında
 * boşluk ya da bindirme oluşmaz. İller, sadeleştirilmiş ilçelerin plaka koduna göre birleştirilmesiyle
 * (dissolve) üretilir; böylece il ve ilçe sınırları birebir çakışır.
 * Sadeleştirme: Douglas–Peucker, metre cinsinden tolerans, küçük parçalar korunur (keep-shapes).
 */
import fs from 'node:fs';
import path from 'node:path';
import mapshaper from 'mapshaper';

const [, , hamDir, ciktiDir] = process.argv;
if (!hamDir || !ciktiDir) { console.error('Kullanım: node yayinla.mjs <ham-klasör> <çıktı-klasör>'); process.exit(2); }
const oku = (f) => JSON.parse(fs.readFileSync(path.join(hamDir, f), 'utf8'));
const ilHam = oku('il-ham.geojson'), ilceHam = oku('ilce-ham.geojson'), rapor = oku('derleme.json');

// ---- Kalite eşikleri: aşılırsa yayın yapılmaz ----
const ESIK = { il: 81, ilceMin: 950, ilceMax: 1000, kapsama: 0.005 };
const hatalar = [];
if (rapor.il_sayisi !== ESIK.il) hatalar.push(`İl sayısı ${rapor.il_sayisi} (beklenen ${ESIK.il})`);
if (rapor.ilce_sayisi < ESIK.ilceMin || rapor.ilce_sayisi > ESIK.ilceMax) hatalar.push(`İlçe sayısı ${rapor.ilce_sayisi} (beklenen ${ESIK.ilceMin}–${ESIK.ilceMax})`);
if ((rapor.kapsama_uyumsuz || []).length) hatalar.push('İlçeleri ilin alanını karşılamayan iller: ' + rapor.kapsama_uyumsuz.map((k) => `${k.il_kodu} ${k.il_adi} (${(k.oran * 100).toFixed(2)}%)`).join(', '));
if ((rapor.ilce_cakismasi || []).length) hatalar.push('Kısmi çakışan ilçeler: ' + rapor.ilce_cakismasi.map((c) => `${c.il_kodu} ${c.ilce_1}/${c.ilce_2} (${c.kesisim_km2} km²)`).join(', '));
const adsiz = ilceHam.features.filter((f) => !f.properties.ilce_adi).length;
if (adsiz) hatalar.push(`${adsiz} ilçenin adı yok`);
if (hatalar.length && !process.env.ESIK_YOKSAY) { console.error('YAYIN DURDURULDU:\n- ' + hatalar.join('\n- ')); process.exit(1); }

fs.mkdirSync(path.join(ciktiDir, 'ilce'), { recursive: true });
const ilAttr = new Map(ilHam.features.map((f) => [f.properties.il_kodu, f.properties]));

async function calistir(komut, girdiler) {
  const out = await mapshaper.applyCommands(komut, girdiler);
  return out;
}
const yazJson = (ad, obj) => fs.writeFileSync(path.join(ciktiDir, ad), typeof obj === 'string' ? obj : JSON.stringify(obj));

async function seviye(tolerans, ek) {
  // ilçe topolojisi → sadeleştir → (a) ilçe çıktısı (b) il = dissolve(il_kodu)
  const girdi = { 'ilce.json': ilceHam };
  const ortak = `-i ilce.json name=ilce -clean -simplify dp interval=${tolerans} keep-shapes`;
  const ilceOut = await calistir(`${ortak} -o ilce${ek}.topo.json format=topojson quantization=1000000 precision=0.000001`, girdi);
  const ilOut = await calistir(`${ortak} -dissolve il_kodu copy-fields=il_adi name=il -o il${ek}.topo.json format=topojson quantization=1000000 precision=0.000001`, girdi);
  return { ilce: JSON.parse(ilceOut[`ilce${ek}.topo.json`]), il: JSON.parse(ilOut[`il${ek}.topo.json`]) };
}

// TopoJSON nesnesindeki geometrilere il özniteliklerini ekle
function ilOzellik(topo) {
  const obj = topo.objects.il || topo.objects[Object.keys(topo.objects)[0]];
  obj.geometries.forEach((g) => {
    const a = ilAttr.get(g.properties.il_kodu) || {};
    g.properties = { il_kodu: g.properties.il_kodu, il_adi: a.il_adi || g.properties.il_adi, ilce_sayisi: a.ilce_sayisi, alan_km2: a.alan_km2, wikidata: a.wikidata || '', osm_id: a.osm_id };
  });
  return topo;
}

const ayrintili = await seviye(30, '');
const sade = await seviye(500, '-sade');
for (const [ad, katman] of [['ayrıntılı', ayrintili.ilce], ['sade', sade.ilce]]) {
  const obj = katman.objects[Object.keys(katman.objects)[0]];
  const var_ = new Set(obj.geometries.filter((g) => g.type).map((g) => String(g.properties.osm_id)));
  const kayip = ilceHam.features.filter((f) => !var_.has(String(f.properties.osm_id))).map((f) => `${f.properties.il_kodu} ${f.properties.ilce_adi} (osm ${f.properties.osm_id})`);
  if (kayip.length && !process.env.ESIK_YOKSAY) { console.error(`YAYIN DURDURULDU: ${ad} katmanda geometrisi kaybolan ilçe: ${kayip.join(', ')}`); process.exit(1); }
}
yazJson('il.topo.json', ilOzellik(ayrintili.il));
yazJson('il-sade.topo.json', ilOzellik(sade.il));
yazJson('ilce-sade.topo.json', sade.ilce);

// Her ilin ayrıntılı ilçeleri: aynı (ortak) topolojiden bölünür, il sınırları komşu dosyalarla çakışır
const bolunmus = await calistir('-i ilce.json name=ilce -clean -simplify dp interval=30 keep-shapes -split il_kodu -o format=topojson singles quantization=1000000 precision=0.000001', { 'ilce.json': ilceHam });
let say = 0;
for (const [ad, icerik] of Object.entries(bolunmus)) {
  const kod = (ad.match(/(\d{2})\.json$/) || [])[1];
  if (!kod) continue;
  const topo = JSON.parse(icerik); const key = Object.keys(topo.objects)[0];
  topo.objects = { ilce: topo.objects[key] };
  fs.writeFileSync(path.join(ciktiDir, 'ilce', kod + '.topo.json'), JSON.stringify(topo)); say++;
}
if (say !== rapor.il_sayisi && !process.env.ESIK_YOKSAY) { console.error(`İl başına ilçe dosyası ${say}, il ${rapor.il_sayisi}`); process.exit(1); }

// Özet: arayüz listesi için (geometri olmadan)
function bbox(fc, kod, alan) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  fc.features.filter((f) => f.properties[alan] === kod).forEach((f) => (function w(x) { if (typeof x[0] === 'number') { b[0] = Math.min(b[0], x[0]); b[1] = Math.min(b[1], x[1]); b[2] = Math.max(b[2], x[0]); b[3] = Math.max(b[3], x[1]); } else x.forEach(w); })(f.geometry.coordinates));
  return b.map((v) => +v.toFixed(5));
}
const ozet = {
  veri_tarihi: rapor.veri_tarihi, derleme_zamani: rapor.derleme_zamani,
  kaynak: '© OpenStreetMap katkıcıları', lisans: 'ODbL 1.0', lisans_url: 'https://opendatacommons.org/licenses/odbl/1-0/',
  tolerans_m: { ayrintili: 30, sade: 500 }, kiyidan_kirpildi: rapor.kiyidan_kirpildi,
  il_sayisi: rapor.il_sayisi, ilce_sayisi: rapor.ilce_sayisi,
  iller: ilHam.features.map((f) => {
    const p = f.properties;
    return { kod: p.il_kodu, ad: p.il_adi, alan_km2: p.alan_km2, wikidata: p.wikidata, osm_id: p.osm_id, bbox: bbox(ilHam, p.il_kodu, 'il_kodu'),
      ilceler: ilceHam.features.filter((g) => g.properties.il_kodu === p.il_kodu).map((g) => ({ ad: g.properties.ilce_adi, alan_km2: g.properties.alan_km2, wikidata: g.properties.wikidata, osm_id: g.properties.osm_id })) };
  })
};
yazJson('ozet.json', JSON.stringify(ozet));

// Boyut raporu
const boyut = (f) => (fs.statSync(path.join(ciktiDir, f)).size / 1024).toFixed(0) + ' KB';
console.log('il.topo.json', boyut('il.topo.json'), '| il-sade', boyut('il-sade.topo.json'), '| ilce-sade', boyut('ilce-sade.topo.json'), '| ozet', boyut('ozet.json'), '| il başına ilçe dosyası', say);
const enBuyuk = fs.readdirSync(path.join(ciktiDir, 'ilce')).map((f) => [f, fs.statSync(path.join(ciktiDir, 'ilce', f)).size]).sort((a, b) => b[1] - a[1])[0];
if (enBuyuk) console.log('en büyük il dosyası', enBuyuk[0], (enBuyuk[1] / 1024).toFixed(0) + ' KB');
if (hatalar.length) console.log('UYARI (eşikler yok sayıldı):', hatalar.join(' | '));
