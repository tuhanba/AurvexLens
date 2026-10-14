# AURVEX LENS — Claude Code Task Pack P0
**Faz 0: Proje iskeleti, salt-okuma veri bağlantısı, veri uygunluk raporu**

Sürüm: 0.1 · Hazırlanma: 2026-10-14 · Durum: TASLAK
Ön koşul: §1'deki maddeler kullanıcı tarafından teyit edilmeden canlı MT5 adımları çalıştırılmaz.

> Bu dosya, kullanıcının verdiği AURVEX_LENS_CLAUDECODE_TASKPACK_P0.md belgesinin repodaki kopyasıdır.

---

## 0. Bu belgenin kapsamı

Aurvex Lens, MT5 grafik ekran görüntüsünden başlayıp doğrulanmış broker verisiyle gerekçeli analiz ve koşullu işlem planı üreten kişisel bir karar destek uygulamasıdır. Emir göndermez.

Bu paket yalnızca **Faz 0**'ı tanımlar:
- proje iskeleti,
- salt-okuma MT5 bağlantısı ve kimlik doğrulaması,
- ham veri çekimi,
- ayrı kriterlerle veri uygunluk raporu.

Faz 0'da strateji, backtest, AI çağrısı, web arayüzü ve risk motoru **yoktur**.

---

## 1. Ön koşullar (kullanıcı teyidi — kod yok)

| # | Teyit | Durum |
|---|---|---|
| P1 | Windows makinenin piyasa saatlerinde açık kalma düzeni (sürekli / sadece çalışırken) | BEKLİYOR |
| P2 | Mevcut EA terminalinden **ayrı** bir MT5 kurulumu yapılabilir; kurulum yolu belirlendi (öneri: `C:\AurvexLens\mt5\`) | BEKLİYOR |
| P3 | FTMO hesabı için investor (salt-okuma) şifresi mevcut; ayrı terminalde **kullanıcı tarafından elle** bu şifreyle giriş yapıldı | BEKLİYOR |
| P4 | Mevcut EA terminalinin kurulum yolu (yasak yol listesi için) | BEKLİYOR |
| P5 | FTMO programı, aşaması, hesap büyüklüğü (Faz 0'da kullanılmaz; kural kaydı için) | BEKLİYOR |
| P6 | Sembol adı ayrı terminalde tam olarak nasıl görünüyor (`XAGUSD`, `XAGUSD.` vb.) | BEKLİYOR |

Kimlik bilgileri (şifreler) hiçbir zaman Aurvex Lens konfigürasyonuna, koduna veya loglarına girmez. Bağlantı, kullanıcının zaten oturum açtığı terminale **yol ile** bağlanarak yapılır.

---

## 2. Kararlar

### 2.1 Kesinleşen kararlar
- D1 — Ürün: grafik yükle → bilgileri doğrula → analiz → koşullu plan → sonuç takibi. Ölçüm altyapısı bu deneyimin omurgasıdır; ürünün kendisi değildir.
- D2 — Mimari: Windows'ta yerel çalışma; Python hesaplama motoru; yerel veri köprüsü; mobil uyumlu web arayüzü (Faz 1+).
- D3 — Emir yok. Hiçbir sürümde emir açma/değiştirme/kapatma yok.
- D4 — İlk enstrüman XAGUSD; ekran görüntüsü kaynağı MT5. TradingView kapsam dışı (v1).
- D5 — Mevcut EA terminali, hesabı ve ayarları değiştirilmez; o terminale bağlanılmaz.
- D6 — Plan durumları ayrıdır; hiçbiri açıklamasız "BEKLE" altında birleştirilmez (§2.3).
- D7 — Plan kayıtları append-only; revizyon yeni kayıt oluşturur, eskisini değiştirmez.
- D8 — Simülasyon sonuçları ile kullanıcının gerçek işlemleri ayrı tablolarda tutulur.
- D9 — FTMO kuralları yalnızca resmî FTMO kaynağı + kullanıcı hesap bilgisinden, sürümlü kayıt olarak tutulur (URL, doğrulama tarihi, ürün, aşama).
- D10 — Başlangıç zaman dilimi **hipotezi**: H1 bağlam / M15 yapı / M5 giriş, 30–120 dk ufuk. Kanıtlanmış optimum değildir; test kapsamıdır.

### 2.2 Açık kararlar
- O1 — Ayrı terminal + investor erişiminin uygulanabilirliği (Faz 0 kimlik testleriyle doğrulanacak).
- O2 — Veri uygunluk eşikleri (§6.2'deki öneriler kullanıcı onayı bekler; canlı rapor görülmeden onaylanır).
- O3 — Broker sunucu saat dilimi kuralı ve tarihsel DST eşlemesi (Faz 0 ölçecek, kullanıcı onaylayacak).
- O4 — Ekonomik takvim kaynağı (MT5 dahili takvimi MQL5 export ile mi, harici sağlayıcı mı). Karar verilene kadar sistem "haber kontrolü yapılmadı" gösterir.
- O5 — İlk strateji ve ön-kayıt protokolü (Faz 1 öncesi, sonuçlara bakılmadan dondurulacak).
- O6 — AI'a gönderilecek veri kapsamı (§4) ve dolar değerlerinin AI'a hiç gönderilmeyip arayüzde şablonla doldurulması önerisi.
- O7 — Telefondan uzak erişim yöntemi (Faz 0'da yok; sunucu yalnızca 127.0.0.1).
- O8 — Mevcut collector'ın yeniden kullanımı (dosyalar incelenmeden karar yok).

### 2.3 Plan/analiz durum taksonomisi (Faz 1'de uygulanacak, şimdiden sabit)

| Kod | Anlamı |
|---|---|
| `INPUT_UNCONFIRMED` | Görselden okunan sembol/zaman dilimi kullanıcı tarafından onaylanmadı |
| `DATA_INSUFFICIENT` | Veri kabul kriterlerinden en az biri FAIL/UNKNOWN; hangisi olduğu gösterilir |
| `NO_SETUP` | Veri yeterli; tanımlı strateji kurallarının hiçbiri koşulu karşılamıyor |
| `RISK_NOT_ALLOWED` | Kurulum var; risk/limit kontrolü geçmiyor veya limit hesabı için veri eksik |
| `PLAN_RESEARCH` | Kurulum var, risk uygun; **strateji avantajı henüz doğrulanmadı** etiketiyle |
| `PLAN_VALIDATED` | Strateji, ön-kayıtlı doğrulama protokolünü geçti (henüz hiçbir strateji bu durumda değil) |

Her plana bağımsız bayraklar eklenir: `NEWS_UNCHECKED`, `NEWS_RULE_UNVERIFIED`, `NEWS_STRATEGY_UNTESTED`.
Haber kuralı açısından izinli olmak (FTMO kuralı) ile haber sırasında stratejinin güvenilir olması (test kapsamı) ayrı kontrollerdir.

### 2.4 Sonuç takibi durum makinesi (Faz 1'de uygulanacak)

```
CREATED
 ├─ CANCELLED_INVALIDATED      (giriş öncesi geçersizlik koşulu)
 ├─ EXPIRED_NOT_TRIGGERED      (geçerlilik süresi doldu, tetik yok)
 ├─ SUPERSEDED                 (yeni revizyon; eski kayıt değişmez)
 ├─ UNRESOLVED_DATA_GAP        (takip penceresinde veri kesintisi)
 └─ ENTERED_SIM
     ├─ EXIT_SL / EXIT_TP1_PARTIAL → EXIT_TP2 / EXIT_SL_AFTER_TP1 / EXIT_TIME
     ├─ AMBIGUOUS_SAME_BAR     (aynı barda SL ve TP; tick yoksa sıra varsayılmaz)
     └─ UNRESOLVED_DATA_GAP
```
"Plan oluşturuldu" ≠ "işlem açıldı". Gerçek işlemler ayrı tabloda, kullanıcı onayıyla eşleştirilir.

---

## 3. Güvenlik ve izolasyon sınırları

Birincil sınırlar (broker/terminal seviyesinde):
1. **Ayrı terminal**: Aurvex Lens yalnızca konfigürasyondaki açık `terminal_path`'e bağlanır (`initialize(path=...)`). `login`/`password`/`server` parametreleri **hiçbir zaman** verilmez.
2. **Investor erişimi**: Terminale kullanıcı elle investor şifresiyle girer. Investor oturumunda broker emir kabul etmez.
3. **Kimlik doğrulaması** (köprü başlarken, tümü geçmezse süreç çıkar; kimlik dışında veri okunmaz):
   - `terminal_info().path` == konfigüre edilen yol
   - konfigüre yol, `forbidden_terminal_paths` listesinde değil (EA terminali)
   - `account_info().login` == `expected_login` (yerel, git'e girmeyen konfigürasyon)
   - `account_info().server` == `expected_server`
   - `account_info().trade_allowed` == False (investor oturumu beklentisi)
   - `terminal_info().trade_allowed` (Algo Trading düğmesi) — False beklenir; True ise uyarı
   **Not:** Bu alanların investor oturumundaki davranışı Faz 0'da ampirik olarak doğrulanır. Bir alan beklenen biçimde davranmıyorsa sonuç `UNKNOWN` olur ve süreç kullanıcıya sormak için durur; varsayımla devam edilmez.

İkincil sınırlar (kod seviyesinde, tek başına yeterli sayılmaz):
4. `MetaTrader5` modülü yalnızca `bridge/mt5_readonly.py` içinde import edilir. Dışarıya sadece beyaz listedeki okuma fonksiyonları açılır.
5. Statik test: kaynak kodda `order_send`, `order_check`, `order_calc_*` dışındaki emir/pozisyon değiştiren çağrılar ve `initialize(` içinde `login`/`password` kullanımı CI testinde FAIL.
6. Faz 0'da ağ sunucusu yok. Faz 1+ web sunucusu varsayılan olarak `127.0.0.1`'e bağlanır.
7. Log ve raporlarda hesap numarası maskelenir (`****1234`).
8. Faz 0 MQL5 script/EA çalıştırmaz, terminal ayarı değiştirmez.

---

## 4. Dış veri çıkışı politikası

Doğru ifade: **Veriler makineden yalnızca dış AI API'sine gönderildiğinde çıkar; neyin gideceği aşağıda sınırlanır.**

- Faz 0: dışarı hiçbir veri gönderilmez. AI çağrısı yoktur.
- Faz 1+ önerisi (O6, onay bekliyor):
  - Gönderilir: kullanıcının kırptığı grafik alanı, onaylanmış sembol/zaman dilimi, motorun hesapladığı yapısal sonuçlar (seviyeler, durum kodları, oranlar).
  - Gönderilmez: hesap numarası, sunucu adı, bakiye/equity mutlak değerleri, açık pozisyon ayrıntıları, şifre/anahtar.
  - Dolar riski, lot ve P&L rakamları AI'a gönderilmez; AI anlatımı `{risk_usd}` gibi yer tutucularla yazılır, arayüz motor çıktısıyla doldurur. Bu, AI'ın sayı değiştirememesini yapısal olarak garanti eder.
  - Görselde MT5 başlık çubuğu/hesap paneli görünüyorsa gönderim öncesi kırpma zorunlu ve önizlemesi gösterilir.
  - Her gönderim bir `egress_log` kaydı oluşturur (ne, ne zaman, hangi sağlayıcı, boyut).

---

## 5. Faz 0 kapsamı

| ID | İş | Çıktı |
|---|---|---|
| P0.1 | Proje iskeleti, `CLAUDE.md`, konfigürasyon şablonu, test altyapısı | Repo |
| P0.2 | Salt-okuma köprü + kimlik doğrulaması (§3) | `aurvex-lens identity` komutu |
| P0.3 | Kimlik alanlarının investor oturumundaki davranışının kaydı | `identity_report.json` |
| P0.4 | Sembol envanteri: `symbol_info` tam döküm, sembol adı eşlemesi | `symbol_snapshot.json` |
| P0.5 | Ham veri çekimi: H1, M15, M5, M1 için mümkün olan en eski bara kadar; tick için kapsam sondajı | Immutable Parquet snapshot'ları |
| P0.6 | Kalite ölçümleri (§6) | `report.md` + `report.json` |
| P0.7 | Erişim sondajı: investor oturumunda `history_deals_get`, `positions_get` ne döndürüyor (yalnızca sayım ve alan adları; içerik rapora girmez) | Raporda bölüm |

### Zaman damgası kuralı
MT5 bar `time` alanı broker sunucu saatidir; epoch biçiminde gelir ama UTC **değildir**. Ham veride sütun adı `time_server` olur. `time_utc` sütunu yalnızca saat dilimi kuralı (O3) kullanıcı tarafından onaylandıktan sonra türetilir. Faz 0'da UTC'ye dönüştürülmüş veri "onaylanmamış" etiketi taşır.

### Snapshot kuralı
Her çekim yeni klasöre yazılır: `data/raw/<extraction_id>/`. Asla üzerine yazılmaz. Yanında `meta.json`: `extraction_id`, çekim UTC zamanı, terminal build, MetaTrader5 paket sürümü, sembol, TF, istenen aralık, dönen satır sayısı, ilk/son `time_server`, dosya sha256.

---

## 6. Veri uygunluk kriterleri

Tek kalite skoru yoktur. Her kriter ayrı `PASS` / `FAIL` / `UNKNOWN` döner; `UNKNOWN` asla `PASS` sayılmaz.

### 6.1 Kriterler ve ölçüm yöntemi

**C1 — Geçmiş kapsamı**
Her TF için ilk ve son bar, takvim süresi, beklenen işlem saatine göre bar sayısı. Tick için: geriye doğru örnek pencerelerle (ör. her ay başından 1 saat) en eski erişilebilir tick tarihi.

**C2 — Eksik veri (piyasa kapanışından ayrılmış)**
Barlar arası boşluklar sınıflanır:
- `EXPECTED_CLOSURE`: hafta sonu ve tekrar eden günlük kapanış/ara. Program, verideki tekrar eden desenden **aday** olarak çıkarılır ve resmî FTMO işlem saatleri ile kullanıcı tarafından teyit edilir. Teyit yoksa sınıf `CLOSURE_CANDIDATE` kalır.
- `HOLIDAY_CANDIDATE`: tekil tam/kısmi gün kapanışları; tarih listesi kullanıcı teyidine sunulur.
- `UNEXPLAINED`: yukarıdakilere uymayan boşluklar.
Yalnızca `UNEXPLAINED` veri kesintisi sayılır. Ayrıca TF'ler arası tutarlılık: M1'den yeniden örneklenen M5/M15/H1 ile terminalin M5/M15/H1 OHLC'si karşılaştırılır.

**C3 — Fiyat güncelliği**
`symbol_info_tick` zamanı ile sistem UTC saati farkı (sunucu saat farkı onaylıysa). Piyasa açıkken ölçülür; kapalıyken `NOT_APPLICABLE_MARKET_CLOSED`. Ayrıca `terminal_info().connected`.

**C4 — Saat doğruluğu**
- Yerel saat: Windows saat senkronizasyon durumu raporlanır.
- Güncel sunucu farkı: son tick `time_msc` vs sistem UTC.
- **Tarihsel DST eşlemesi**: güncel fark tüm geçmişe uygulanmaz. Aday kurallar (ör. sabit offset, EU DST'li, US DST'li) her hafta için test edilir: haftalık açılış/kapanış ve günlük ara zamanlarının UTC karşılığı hangi kuralda sabit kalıyor? ABD ve AB DST geçişlerinin ayrıştığı haftalar (Mart ve Ekim/Kasım) ayırt edici test olarak ayrı raporlanır. İkinci kontrol: yayın saati resmî olarak bilinen yüksek etkili veri anlarında (ör. ABD istihdam verisi) volatilite sıçramasının hangi bara düştüğü. Sonuç: hafta bazında `rule_match` tablosu; açıklanamayan hafta sayısı.

**C5 — Maliyet verisinin yeterliliği**
Her bileşen için kaynak durumu: `VERIFIED` (iki bağımsız kaynak uyumlu), `SINGLE_SOURCE`, `MISSING`.
- Spread: tick bid/ask'ten saat/seans bazlı dağılım (tick kapsamı neredeyse). Bar `spread` alanı gerçek spread **varsayılmaz**; tick bulunan pencerelerde bar spread'inin bar içi tick spread'inin min/ortalama/açılış/kapanış değerlerinden hangisine karşılık geldiği ölçülür ve raporlanır. Bu doğrulanana kadar bar spread "gösterge" etiketlidir.
- Komisyon: `symbol_info` içinde bulunduğu varsayılmaz. Kaynaklar: kullanıcının gerçek işlem kayıtlarındaki komisyon alanı (investor erişimiyle okunabiliyorsa — P0.7) ve resmî FTMO enstrüman/sözleşme bilgisi (kullanıcı sağlar).
- Swap: `symbol_info` swap alanları + resmî kaynak.
- Sözleşme özellikleri (contract size, tick size/value, min lot, lot adımı): `symbol_info` + resmî kaynak.
- Slippage: tarihsel ölçüm yok → `MISSING`. Faz 1'de tek bir "muhafazakâr" sayı yerine önceden tanımlı birden çok senaryo raporlanır.

**C6 — Bid/ask yürütme hazırlığı (bilgi amaçlı)**
Bar OHLC'nin bid mi olduğu tick verisiyle doğrulanır. Faz 1 yürütme kuralları için not: alış girişi ask'te, alış stop'u bid ile tetiklenir; satış tersi. Bar verisinde o anki spread bilinmediği için yürütme maliyeti senaryolarla modellenir.

**C7 — Takvim kapsamı**
Faz 0'da takvim yok → `NEWS_CALENDAR: NOT_CONNECTED`. Rapor bunu açıkça yazar; hiçbir bölüm "haber açısından güvenli" ifadesi içermez.

### 6.2 Eşikler (ÖNERİ — kullanıcı onayı bekliyor, canlı rapor görülmeden onaylanır)

`config/quality_thresholds.toml` dosyasında tutulur; raporda dosyanın sha256'sı yazılır. Onaydan sonra değişirse rapor bunu gösterir.

| Kriter | Önerilen eşik |
|---|---|
| C1 | M5, M15, H1 ≥ 24 ay; M1 ≥ 12 ay. Tick: eşik yok, kapsam raporlanır |
| C2 | `UNEXPLAINED` boşluk oranı ≤ %0.1 (TF başına beklenen bar); tek `UNEXPLAINED` boşluk ≤ 30 dk; tüm kapanış adayları kullanıcı teyitli |
| C3 | Piyasa açıkken son tick yaşı ≤ 10 sn (normal tick sıklığı ölçülüp gerekirse revize) |
| C4 | Yerel saat senkron; tarihsel her hafta onaylı kurala uyuyor, açıklanamayan hafta = 0 |
| C5 | Faz 1 için: spread dağılımı tick'ten, komisyon ve sözleşme özellikleri `VERIFIED` |

**Faz 0 görevinin tamamlanması ≠ verinin uygun çıkması.** Görev, rapor doğru üretildiğinde biter; Faz 1'e geçiş kararı rapordaki kriter sonuçlarına göre ayrıca verilir.

---

## 7. Proje klasör yapısı

Önerilen konum: `C:\AurvexLens\` (mevcut EA/collector/AurvexAI dizinlerinden ayrı).

```
C:\AurvexLens\
├─ mt5\                         # ayrı MT5 kurulumu (kullanıcı kurar; repo dışı)
└─ aurvex-lens\                 # git repo
   ├─ README.md
   ├─ CLAUDE.md                 # Claude Code proje kuralları
   ├─ pyproject.toml
   ├─ .gitignore                # data/, config/local.toml, *.log
   ├─ docs\
   │  ├─ 00_decisions.md        # §2 (kesin/açık kararlar, ADR formatı)
   │  ├─ 01_safety_boundaries.md# §3, §4
   │  ├─ 02_data_quality.md     # §6
   │  ├─ 03_phase0_spec.md      # bu paketin tamamı
   │  └─ rules\                 # FTMO kural kayıtları (Faz 1; Faz 0'da boş + şema)
   ├─ config\
   │  ├─ lens.example.toml      # terminal_path, expected_login, expected_server, forbidden_terminal_paths, symbol
   │  └─ quality_thresholds.toml
   ├─ src\aurvex_lens\
   │  ├─ bridge\
   │  │  ├─ mt5_readonly.py     # MetaTrader5'in import edildiği TEK dosya; beyaz liste
   │  │  └─ identity.py         # §3 kimlik kontrolleri
   │  ├─ data\
   │  │  ├─ extract.py
   │  │  ├─ snapshot.py         # immutable yazım + meta.json + sha256
   │  │  └─ schema.py
   │  ├─ quality\
   │  │  ├─ coverage.py         # C1
   │  │  ├─ gaps.py             # C2
   │  │  ├─ freshness.py        # C3
   │  │  ├─ server_time.py      # C4
   │  │  ├─ costs.py            # C5, C6
   │  │  └─ report.py           # md + json, PASS/FAIL/UNKNOWN
   │  ├─ common\
   │  │  ├─ masking.py
   │  │  └─ provenance.py
   │  └─ cli.py                 # aurvex-lens identity | extract | report
   ├─ tests\
   │  ├─ fixtures\synthetic\    # SENTETİK — piyasa verisi değil
   │  ├─ test_no_trade_calls.py # statik güvenlik testi
   │  ├─ test_identity.py       # sahte MT5 yanıtlarıyla
   │  ├─ test_gaps.py
   │  ├─ test_server_time.py
   │  └─ test_snapshot.py
   └─ data\                     # gitignored
      ├─ raw\<extraction_id>\
      └─ reports\<extraction_id>\
```

### CLAUDE.md içeriği (Claude Code oluşturacak)
- Bu proje emir göndermez. Emir/pozisyon değiştiren MT5 çağrıları yazılmaz.
- `MetaTrader5` yalnızca `bridge/mt5_readonly.py` içinde import edilir.
- `initialize()` yalnızca `path=` ile çağrılır; login/şifre/sunucu parametresi yasak.
- Mevcut EA terminaline, yoluna veya ayar dosyalarına dokunulmaz.
- Sentetik veri yalnızca `tests/fixtures/synthetic/` altında; çıktılarında `SYNTHETIC — NOT MARKET DATA` etiketi zorunlu.
- Ölçülemeyen değer `UNKNOWN`/`MISSING` olarak raporlanır; tahmin veya varsayılan değerle doldurulmaz.
- `time_server` UTC değildir; onaylı saat dilimi kuralı olmadan UTC etiketi verilmez.
- Ham snapshot'lar asla üzerine yazılmaz.
- Hesap numarası loglarda/raporlarda maskelenir.
- Canlı MT5 komutları kullanıcı açıkça "çalıştır" demeden çalıştırılmaz.

---

## 8. Görev kabul kriterleri (P0)

| ID | Kriter |
|---|---|
| A1 | `pytest` MT5 olmadan geçer; tüm testler sentetik fixture kullanır |
| A2 | `test_no_trade_calls.py`: yasak çağrılar ve `initialize` içinde login/şifre kullanımı tespit edilince test FAIL veriyor (negatif test dahil) |
| A3 | Kimlik kontrolü: yanlış yol / yasak yol / farklı login / farklı sunucu / `trade_allowed=True` durumlarının her biri için süreç sıfırdan farklı kodla çıkıyor ve kimlik dışında veri okumuyor (sahte MT5 ile test) |
| A4 | Canlı `identity` çalıştırması `identity_report.json` üretiyor; her alan için gözlenen değer + beklenen + sonuç; hesap numarası maskeli |
| A5 | `extract` her TF için snapshot + `meta.json` + sha256 üretiyor; ikinci çalıştırma yeni klasör açıyor, eskisini değiştirmiyor |
| A6 | `report` C1–C7'nin her biri için ayrı sonuç, metrik, yöntem açıklaması ve kanıt dosya yolu yazıyor; tek "kalite skoru" yok |
| A7 | Rapor başlığında: `CANLI VERİ`, extraction_id, terminal build, paket sürümü, eşik dosyası sha256, `NEWS_CALENDAR: NOT_CONNECTED` |
| A8 | Raporda `time_utc` içeren her tablo "saat dilimi kuralı onaylanmadı" etiketi taşıyor (O3 kapanana kadar) |
| A9 | Repo `config/local.toml` ve `data/` içermiyor (.gitignore doğrulandı) |
| A10 | `README.md` Windows kurulum ve çalıştırma adımlarını içeriyor; her komut ayrı satırda, zincirleme yok |

---

## 9. Kapsam dışı (Faz 0)

Strateji, backtest, benzerlik araması, risk/lot motoru, FTMO kural motoru, AI/görsel okuma, web arayüzü, uzak erişim, ekonomik takvim, collector entegrasyonu, MQL5 script/EA, terminal ayarı değişikliği.

---

## 10. Claude Code ilk görev promptu

Aşağıdaki metin doğrudan yapıştırılabilir.

```
Görev: Aurvex Lens — Faz 0 (P0.1–P0.7)

Bağlam: Aurvex Lens, MT5'ten salt-okuma veriyle çalışan kişisel bir analiz uygulaması. Bu görev yalnızca proje iskeleti, salt-okuma MT5 köprüsü ve veri uygunluk raporunu kapsıyor. Tam spesifikasyon: AURVEX_LENS_CLAUDECODE_TASKPACK_P0.md (bu dosyayı docs/03_phase0_spec.md olarak repoya kopyala ve önce baştan sona oku).

Mutlak kurallar:
1. Emir gönderen, değiştiren veya kapatan hiçbir MT5 çağrısı yazma. MetaTrader5 modülünü yalnızca src/aurvex_lens/bridge/mt5_readonly.py içinde import et.
2. mt5.initialize() yalnızca path= ile çağrılır. login, password, server parametresi kullanma.
3. Mevcut EA terminaline, onun kurulum dizinine, AurvexAI veya collector dizinlerine dokunma, okuma veya yazma.
4. Uydurma veri üretme. Ölçülemeyen her değer UNKNOWN veya MISSING olarak raporlanır. Sentetik veri sadece tests/fixtures/synthetic/ altında ve "SYNTHETIC — NOT MARKET DATA" etiketiyle.
5. MT5 bar time alanını UTC olarak etiketleme; sütun adı time_server.
6. Canlı MT5'e bağlanan hiçbir komutu ben açıkça "canlı çalıştır" demeden çalıştırma. Önce sahte MT5 ile tüm testleri geçir.

Adımlar:
1. C:\AurvexLens\aurvex-lens altında spesifikasyon §7'deki yapıyı oluştur. git init. CLAUDE.md'yi §7'deki kurallarla yaz. docs/00–02'yi spesifikasyonun ilgili bölümlerinden oluştur.
2. pyproject.toml: Python sürümünü MetaTrader5 paketinin güncel desteklediği sürüme göre belirle ve README'ye yaz; bağımlılıklar: MetaTrader5, pandas, pyarrow, pytest, tomli (gerekirse). Sürümleri sabitle.
3. bridge/mt5_readonly.py: beyaz liste — initialize(path), shutdown, version, terminal_info, account_info, symbol_info, symbol_info_tick, symbols_get, copy_rates_from_pos, copy_rates_range, copy_ticks_range, copy_ticks_from, history_deals_total, history_deals_get, positions_total, last_error. Başka fonksiyon dışarı açılmaz.
4. bridge/identity.py: spesifikasyon §3 madde 3'teki kontroller. Herhangi biri başarısızsa veya alan beklenmedik davranırsa sonuç FAIL/UNKNOWN, süreç sıfırdan farklı kodla çıkar.
5. tests/test_no_trade_calls.py: kaynak ağacında yasak çağrıları ve initialize içinde login/password/server kullanımını tarayan test + bunu kanıtlayan negatif test.
6. data/extract.py ve snapshot.py: §5 snapshot kuralı.
7. quality/: C1–C7, §6.1'deki yöntemlerle. Eşikleri config/quality_thresholds.toml'dan oku; dosyada spesifikasyon §6.2'deki değerleri "PROPOSED — user approval pending" yorumuyla yaz.
8. cli.py: aurvex-lens identity | extract | report.
9. README.md: Windows kurulum ve çalıştırma; her komut ayrı satırda, && ile zincirleme yok.
10. pytest'i çalıştır, sonuçları göster.

Bitirince bana şunları raporla:
- Oluşturulan dosya listesi.
- Test sonuçları.
- Spesifikasyonda belirsiz bulduğun veya varsayım yapmak zorunda kaldığın her nokta (varsayım yapmak yerine sormayı tercih et).
- Canlı çalıştırma için benim yapmam gereken ön koşullar (§1) ve çalıştıracağım komutlar.

Canlı çalıştırmayı ben onayladıktan sonra: identity → extract → report sırasıyla çalıştır; identity FAIL/UNKNOWN verirse dur ve bana sor.
```
