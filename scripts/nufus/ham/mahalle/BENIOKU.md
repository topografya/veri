# Mahalle ve köy nüfusu (ham)

Kaynak: TÜİK Merkezi Dağıtım Sistemi (MEDAS, https://biruni.tuik.gov.tr/medas/), konu "Adrese Dayalı Nüfus Kayıt Sistemi Sonuçları",
ölçüm "Belediye, köy ve mahalle nüfusları", 2025, Türkiye geneli. İndirme: 27.10.2026, özgün CSV (ayraç `|`).

| Dosya | Düzey | Kayıt | Nüfus |
|---|---|---|---|
| medas_mahalle_2025_toplam.csv | Mahalle (il/ilçe/belediye/mahalle, TÜİK kodu) | 32.254 | 81.820.423 |
| medas_koy_2025_toplam.csv | Köy (il/ilçe/köy, TÜİK kodu) | 18.183 | 4.260.304 |

Denetim (27.10.2026; ilçe sayıları 28.10.2026'da yayımlanan v2026.10.2 verisiyle yeniden sayıldı, Codex denetimi O4-01): mahalle + köy toplamı 86.080.727; TÜİK Türkiye nüfusu 86.092.168 (fark 11.441, %0,013).
973 ilçenin 880'inde mahalle + köy toplamı ilçe nüfusuna birebir eşit; 93 ilçede birkaç kişiden birkaç bin kişiye kadar eksik
(ör. Sincan, Yenimahalle). Fark TÜİK'in iki tablosu arasındadır; araçta ilçe nüfusu ilçe tablosundan, mahalle nüfusu mahalle tablosundan gösterilir.
MEDAS mahalle düzeyinde cinsiyet kırılımı vermez (yalnız köy ve belediye düzeyinde).
Kullanım: TÜİK yasal uyarısı gereği kaynak gösterilerek ("Kaynak: TÜİK, ADNKS").
