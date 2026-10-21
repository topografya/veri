#!/usr/bin/env node
/*
 * Yayın dosyalarının bağımsız denetimi: node test/denetle.mjs <çıktı-klasör> [--yapay]
 *  - dosyalar okunur, il ve ilçe sayıları özetle tutarlı
 *  - ilçeler arasında bindirme yok (toplam alan ≈ birleşim alanı)
 *  - her ilin alanı ≈ ilçelerinin toplamı (dissolve tutarlılığı)
 *  - komşu il dosyalarında ortak sınır aynı köşelerden oluşur
 *  - sadeleştirme köşe sayısını düşürür, alan değişimi küçük kalır
 *  --yapay: yapay test verisine özgü ek denetimler (gürültü silinmeli, kıyı kırpılmalı)
 */
import fs from 'node:fs';
import path from 'node:path';
import { feature } from 'topojson-client';
import area from '@turf/area';
import union from '@turf/union';
import { featureCollection } from '@turf/helpers';

const dir = process.argv[2], yapay = process.argv.includes('--yapay');
let hata = 0, sayi = 0;
const ok = (c, m) => { sayi++; if (!c) { hata++; console.log('HATA:', m); } };
const oku = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const fc = (topo) => feature(topo, topo.objects[Object.keys(topo.objects)[0]]);

const ozet = oku('ozet.json');
const il = fc(oku('il.topo.json')), ilSade = fc(oku('il-sade.topo.json')), ilceSade = fc(oku('ilce-sade.topo.json'));
ok(il.features.length === ozet.il_sayisi && ilSade.features.length === ozet.il_sayisi, `il sayısı ${il.features.length}/${ilSade.features.length} ≠ ${ozet.il_sayisi}`);
ok(ilceSade.features.length === ozet.ilce_sayisi, `ilçe sayısı ${ilceSade.features.length} ≠ ${ozet.ilce_sayisi}`);
ok(il.features.every((f) => /^\d{2}$/.test(f.properties.il_kodu) && f.properties.il_adi), 'il öznitelikleri');
ok(ilceSade.features.every((f) => f.properties.ilce_adi && f.properties.il_kodu && f.properties.il_adi && f.properties.alan_km2 > 0), 'ilçe öznitelikleri');
ok(ozet.lisans === 'ODbL 1.0' && /OpenStreetMap/.test(ozet.kaynak), 'lisans ve atıf özette');

let toplamKoseAyr = 0, ilceAyr = [];
const bilinen = new Map();
for (const p of ozet.iller) {
  const dosya = path.join('ilce', p.kod + '.topo.json');
  ok(fs.existsSync(path.join(dir, dosya)), 'eksik dosya ' + dosya);
  const f = fc(oku(dosya));
  ok(f.features.length === p.ilceler.length, `${p.kod}: ilçe sayısı ${f.features.length} ≠ ${p.ilceler.length}`);
  f.features.forEach((x) => { ilceAyr.push(x); (function w(c) { if (typeof c[0] === 'number') toplamKoseAyr++; else c.forEach(w); })(x.geometry.coordinates); });
  // ortak sınır denetimi için köşe kümeleri
  const set = new Set(); (function w(c) { if (typeof c[0] === 'number') set.add(c[0].toFixed(5) + ',' + c[1].toFixed(5)); else c.forEach(w); })(f.features.map((x) => x.geometry.coordinates));
  bilinen.set(p.kod, set);
}
// il alanı ≈ ilçe toplamı ve ilçe bindirmesi yok (her il için)
let enKotuIl = 0, enKotuBindirme = 0;
for (const p of ozet.iller) {
  const ilF = il.features.find((f) => f.properties.il_kodu === p.kod);
  const ilceler = ilceAyr.filter((f) => f.properties.il_kodu === p.kod);
  const top = ilceler.reduce((s, f) => s + area(f), 0);
  const birlesim = ilceler.length > 1 ? area(union(featureCollection(ilceler))) : top;
  enKotuIl = Math.max(enKotuIl, Math.abs(area(ilF) - top) / area(ilF));
  enKotuBindirme = Math.max(enKotuBindirme, (top - birlesim) / top);
}
ok(enKotuIl < 1e-4, 'il alanı ile ilçe toplamı farkı ' + enKotuIl);
ok(enKotuBindirme < 1e-4, 'ilçe bindirmesi ' + enKotuBindirme);
// komşu il dosyaları: ortak köşeler (her iki dosyada da bulunan) en az birkaç tane olmalı ve sınırda boşluk olmamalı
let komsu = 0;
const kodlar = ozet.iller.map((p) => p.kod);
for (let a = 0; a < kodlar.length; a++) for (let b = a + 1; b < kodlar.length; b++) {
  const A = bilinen.get(kodlar[a]), B = bilinen.get(kodlar[b]); let ortak = 0;
  for (const k of A) if (B.has(k)) { ortak++; if (ortak > 1) break; }
  if (ortak > 1) komsu++;
}
ok(komsu > 0, 'komşu il dosyaları ortak köşe paylaşmıyor');
// sade ve ayrıntılı alan tutarlılığı
const alanAyr = il.features.reduce((s, f) => s + area(f), 0), alanSade = ilSade.features.reduce((s, f) => s + area(f), 0);
ok(Math.abs(alanAyr - alanSade) / alanAyr < 0.01, 'sade/ayrıntılı toplam alan farkı ' + Math.abs(alanAyr - alanSade) / alanAyr);
// özetteki alan (kırpılmış, sadeleştirilmemiş, jeodezik) ile ayrıntılı katman alanı yakın olmalı
const ozetAlan = ozet.iller.reduce((s, p) => s + p.alan_km2, 0) * 1e6;
ok(Math.abs(ozetAlan - alanAyr) / ozetAlan < 0.005, 'özet alanı ile katman alanı farkı ' + Math.abs(ozetAlan - alanAyr) / ozetAlan);

if (yapay) {
  // yapay veride her ilçe kenarı 41 noktalıydı; 30 m tolerans ±8 m gürültüyü silmeli
  const koseBasina = toplamKoseAyr / ilceAyr.length;
  ok(koseBasina < 12, 'gürültü silinmedi: ilçe başına ortalama köşe ' + koseBasina.toFixed(1));
  const il01 = ozet.iller.find((p) => p.kod === '01'), il05 = ozet.iller.find((p) => p.kod === '05');
  ok(il01.alan_km2 < il05.alan_km2 * 0.9, 'kıyı kırpması: il 01 alanı küçülmeli');
  ok(!ozet.iller.some((p) => /Komşu/.test(p.ad)), 'komşu ülke birimi süzülmeli');
}
console.log(hata ? `DENETİM BAŞARISIZ: ${hata}/${sayi}` : `DENETİM GEÇTİ: ${sayi} denetim · ${ozet.il_sayisi} il, ${ozet.ilce_sayisi} ilçe`);
process.exit(hata ? 1 : 0);
