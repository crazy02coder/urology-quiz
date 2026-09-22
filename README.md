# Bilkent Şehir Hastanesi canlı eğitim

FastAPI, HTML, CSS ve vanilla JavaScript ile tek yönetici şifreli canlı sınav uygulaması. Katılımcılar yalnızca takma adla katılır. Her soru, yöneticinin lobide seçtiği **5–300 saniye** boyunca açık kalır (varsayılan 45 saniye); sonuçtan sonraki soruya yalnızca yönetici geçer. SQLite kayıtları ve WebSocket bağlantıları yenileme/yeniden bağlanmayı destekler.

## Yerelde başlatma

Python 3.11 kullanın. Terminalde:

```bash
cd /projenin/bulundugu/klasor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -c constraints.txt
test -f .env || cp .env.example .env
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Yönetici ekranı: **http://localhost:8000/admin** veya **http://127.0.0.1:8000/admin**. Yerel HTTP kullanımında bu iki adres aynı port için kabul edilir. Başlangıç şifresi `Bilkent.yeni123`; yalnızca sunucunun `.env` dosyasındaki `ADMIN_PASSWORD` değerinden okunur. Frontend içinde şifre bulunmaz. `.env` sürüm kontrolüne ve Docker imajına dahil edilmez.

Daha sonraki açılışlarda:

```bash
cd /projenin/bulundugu/klasor
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Sunucuyu `Ctrl+C` ile durdurun. Klasör adı önemli değildir; komutları `main.py` ve `requirements.txt` bulunan proje kökünde çalıştırın. Yerel veritabanı yolu proje köküne göre çözülür. `.venv` klasörünü başka makineye taşımayın; yeni konumda sanal ortamı yeniden oluşturun. Tek worker kullanın.

### Aynı ağdaki telefonlarla deneme

Telefon ve bilgisayar aynı ağda olmalı. `.env` içindeki `PUBLIC_BASE_URL` değerini bilgisayarınızın yerel IP adresine değiştirin; örneğin `http://192.168.1.25:8000`. `COOKIE_SECURE=false` yerel HTTP denemesi içindir. Sunucuyu yeniden başlatın ve **admin ekranını da aynı IP adresiyle açın**. QR bu adresi içerir. Yerel IP ve portun telefonlardan erişilebilir olması gerekir. `localhost` QR kodu başka telefondan bilgisayara bağlanamaz.

## Kullanım

1. `/admin` üzerinden giriş yapın. Sınav başlığını yazıp DOCX soru dosyasını seçin.
2. Sınavı hazırlama düğmesi dosyayı ayrıştırır ve doğrudan kaydeder; admin önizlemesi açılmaz. Eksik veya çelişkili cevap nedeniyle kayıt reddedilirse Word dosyasını düzeltip yeniden yükleyin.
3. Kayıtlı sınavdan “Canlı oturum oluştur” seçin. QR kodunu yansıtın; PNG indirme ve bağlantı kopyalama kullanılabilir.
4. Katılımcılar takma adla katılır. Lobi listesi canlı güncellenir. “Her soru için süre (saniye)” alanına 5–300 arasında bir değer yazın. “Başlat” seçilen süreyi kaydeder ve yeni katılımı kapatır.
5. Oturumdaki tüm sorular seçtiğiniz süre kadar açık kalır. Oturum başladıktan sonra süre değiştirilemez. Herkes cevap verse bile süre kısalmaz. Katılımcı yalnızca bir cevap verebilir.
6. Süre sonunda doğru şık yeşil ve “✓ Doğru cevap”, diğer şıklar kırmızı görünür. Grafik, cevap vermeyen sayısı ve kaynak açıklaması açılır. “Sonraki soru” yöneticidedir.
7. Son sorudan sonra “Oturumu bitir” seçin. Katılımcı kendi doğru/yanlış/boş sayılarını, yönetici “Cevap kayıtlarını göster” ile soru bazındaki tüm cevapları görür.

Sınavlar tekrar kullanılabilir. Her oynatım yeni bir oturum, yeni QR ve ayrı katılımcı/cevap kayıtları oluşturur. Sınavlara taslak/aktif/arşiv durumları eklenmemiştir.

## DOCX içe aktarma ve düzenleme

Word dosyaları sunucuda **NLTK ve yerel biçim kurallarıyla** okunur. Harici AI servisi, API anahtarı, ücretli abonelik veya kullanım başına ödeme gerekmez. NLTK'nin `RegexpTokenizer` aracı kullanılır; `nltk.download`, dil modeli veya corpus indirmesi yoktur. Python 3.11 ve mevcut Render/Docker build komutları `requirements.txt` üzerinden bağımlılıkları kurar. Render'ın servis ve depolama ücretleri ayrıdır.

`Soru 1`, `Question 1`, `1.`, `1)` gibi başlıklar; `A)`, `a.`, `B:`, `b-` gibi şıklar; aynı satırdaki sıralı A–B–C şıkları ve ayrı `Cevap Anahtarı: 1-B, 2-C` bölümleri tanınır. Word'ün doğrudan tanımlı sayısal/harfli otomatik listeleri de okunur. Tablo hücreleri satır sırasıyla aktarılır ve kontrol notu gösterilir. Her olası Word düzeninin doğru ayrılması garanti edilmez; belirsiz dosyalar düzenlenebilir taslak olarak açılır.

Örnek düzen:

```text
Soru 1 - Konu: Eğitim konusu
Soru metni burada yer alır.
İpucu: İsteğe bağlı ipucu.
A) Birinci seçenek
B) İkinci seçenek
Doğru Cevap & Açıklama:
Cevap: B) İkinci seçenek
Doğru! İsteğe bağlı açıklama.
```

Dosya yükleme işlemi admin önizlemesi açmadan soruları otomatik kaydeder. Eksik veya çelişkili cevaplar tahmin edilmez; kaydetme kurallarını karşılamayan dosya için hata gösterilir ve Word dosyasının düzeltilmesi gerekir.

### Sorulara görsel ekleme

Word içinde `Soru 1` gibi numaralı başlığı ve soru metnini yazın, ardından resmi **şıklar ve ipucu bölümünden önce** ekleyin. PNG, JPG ve WebP resimler ilgili soruya otomatik bağlanır; soru ekranında görünür ve tıklanınca ayrı sekmede büyütülebilir. İpucu, cevap veya açıklama bölümüne eklenen resimler yalnızca sonuçlar açılınca gösterilir. Sonraki soru başlığı yeni soruya geçişi belirler. Ek bir admin önizlemesi veya resim yükleme adımı yoktur.

OCR gerekmez; görsel olduğu gibi gösterilir. Görselin içindeki yazı soru/şık/cevap olarak okunmaz. Tamamen taranmış bir soru yerine soru metni, şıklar ve cevap anahtarını Word'de metin olarak yazın. Resmi numaralı soru başlığından önce koymayın; eşleştirilemeyen veya desteklenmeyen görseller sessizce atılmaz, dosya reddedilir. İnternet bağlantısıyla eklenmiş resimler, Word şekilleri, SVG/EMF ve metin kutuları için PNG/JPG olarak gömülü resim kullanın.

Her soruda en fazla 12 görsel; belgede en fazla 100 farklı görsel desteklenir. Tek görsel 5 MB ve 16 megapikseli, açılmış farklı görseller 15 MB'ı, sorularda tekrarlanan kopyalar dahil kayıt toplamı 20 MB'ı geçemez; DOCX yükleme sınırı yine 5 MB'tır. Resimler SQLite içinde sınavla birlikte tutulur ve mevcut veritabanı yedeklerine dahil olur. Render'da aynı kalıcı veritabanı diski kullanılır; ek hizmet veya AI/OCR ücreti yoktur. Sınav silindiğinde resimleri de silinir. Eski sınavlara görsel eklemek için resimli Word dosyasını yeniden yükleyin.


Kayıtta 1–1000 soru, her soruda 2–5 dolu şık ve tek doğru cevap sunucuda doğrulanır. Soru metni en fazla 3000, şık 1000, konu/ipucu/açıklama alanlarının her biri 5000 karakterdir. Bir hata varsa hiçbir soru kısmen kaydedilmez. Önizleme 1 saat geçerlidir ve oluşturan yönetici oturumuna bağlıdır. **İpucu, açıklama ve doğru cevap, süre dolmadan katılımcı API veya WebSocket mesajına eklenmez.** Tıbbi içerik yorumlanmaz; doğru cevabın içerik açısından kontrolü yöneticidedir.

Yalnızca `.docx`, en fazla **5 MB** dosya ve **250.000 karakter** okunabilir belge metni kabul edilir. Açılmış ZIP toplamı 20 MB, ana XML 8 MB ve numaralandırma XML'i 1 MB ile sınırlıdır. Bozuk/şifreli dosyalar, makrolar, XML DTD/entity ve izlenen değişiklikler reddedilir. Gömülü PNG/JPG/WebP görseller aktarılır; metin kutuları ve desteklenmeyen görseller reddedilir. OCR yoktur. ZIP içeriği diske açılmaz, dış bağlantılar takip edilmez ve dosyalar harici bir hizmete gönderilmez.

Sağlanan `Uroloji_Asistan_Vaka_Sorulari.docx` dosyası 10 soru ve her soruda 4 şık içerir. Kaynak cevap anahtarı: **B, C, B, D, A, A, C, D, D, A**. Kaynak dosya değiştirilmemiştir; kopyası `tests/fixtures/uroloji.docx` içindedir.

## Oturum ve güvenlik

- Yönetici oturumu 12 saat geçerli, sunucuda hash olarak saklanan rastgele token ile tanınır. Çerez `HttpOnly`, `SameSite=Strict`; HTTPS'de ayrıca `Secure` kullanır. Çıkış sunucu oturumunu iptal eder; açık yönetici WebSocket'i de kapanır.
- Başarısız girişler IP başına 15 dakikada 5 denemeyle sınırlıdır; sayaçlar SQLite'da kalır. Ters proxyde gerçek istemci IP'si yalnızca güvenilen proxylerden alınmalıdır.
- Yazma istekleri `PUBLIC_BASE_URL` origin kontrolü ve özel istek başlığı gerektirir. Yalnızca yerel HTTP yapılandırmasında aynı porttaki localhost/127.0.0.1/IPv6 loopback adresleri eşdeğer kabul edilir; HTTPS/Render için tam origin eşleşmesi korunur. Yönetici yazmalarında ayrıca CSRF token kontrolü vardır. WebSocket origin ve oturum doğrulaması yapar; WebSocket üzerinden kontrol/cevap komutu kabul edilmez.
- Katılımcı token'ları sunucuda hash olarak saklanır; takma ad yetki sağlamaz. Takma adlar NFKC normalizasyonu, baş/son boşluk temizliği ve büyük/küçük harf eşleştirmesiyle aynı oturumda benzersizdir. Katılımcı çerezi 7 gün saklanır. Cihaz/tarayıcı değiştirmek veya çerezi silmek katılımcı kimliğini kaybettirir.
- Veritabanı benzersizlik kuralları ve atomik işlemler yinelenen cevapları engeller. Aynı cevap açık soru içinde güvenle tekrar gönderilebilir; değiştirilemez. Süre bitince tekrarlar dahil tüm cevap istekleri reddedilir. Yönetici kontrolü beklenen oturum sürümünü, oturum oluşturma ise istek kimliğini kullanır.
- Soru bitiş zamanı UTC Unix zaman damgası olarak saklanır. Yöneticinin seçtiği süre dolunca sunucu cevap kabulünü kapatır. Süre oturum kaydında tutulur; bir sonraki soru da aynı süreyle başlar. Yeniden başlatma kalan süreyi sıfırlamaz; süresi geçmiş soru sonuç aşamasına geçer.
- Canlı durumlar WebSocket üzerinden en geç yaklaşık 0,5 saniyede yenilenir. Görsel sayaç sunucunun kalan süresi ve tarayıcının monoton saatiyle çalışır; kabul kararını her zaman sunucu verir. Bağlantı kaybında yeniden bağlanılır ve güncel durum alınır.
- Tek instance/worker mimarisi hedeflenmiştir. Çoklu instance ve yüksek eşzamanlı katılımcı kapasitesi için yük testi ve paylaşımlı yayın/veritabanı mimarisi gerekir; bu sürümde kapasite iddiası yoktur.

## Render kurulumu

Bu çalışma **deploy edilmemiştir**. Aşağıdaki adımlar yayınlama kararı verdiğinizde uygulanır.

Render ücretsiz web servisinin dosya sistemi geçicidir: SQLite dosyaları yeniden deploy, yeniden başlatma veya uykuya geçme sırasında kaybolabilir. Kalıcı disk ücretsiz servise bağlanamaz; **ücretli servis ve kalıcı disk gerekir**. Kaynaklar: [Render ücretsiz servisler](https://render.com/docs/free), [kalıcı diskler](https://render.com/docs/disks).

1. Bu klasörün içeriğini kendi Git deposuna ekleyin. `.env`, `.venv`, `data`, yedek ve test sonuçlarını eklemeyin.
2. Render’da **New → Web Service**, Git deposu, **Python 3** runtime ve ücretli plan seçin. Dosyalar deponun kökündeyse **Root Directory alanını boş bırakın**. Başka bir alt klasöre taşırsanız yalnızca bu alana yeni alt klasörü yazın. Alternatif olarak depodaki `render.yaml` ile Blueprint oluşturun; dosya artık Python runtime kullanır.
3. **Tek instance**, otomatik deploy kapalı; sağlık kontrolü `/healthz`. Aşağıdaki komutları Render alanlarına doğrudan yapıştırın:

   **Build Command**
   ```bash
   pip install -r requirements.txt -c constraints.txt
   ```

   **Start Command**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers
   ```

   Bu giriş noktası kökteki `main.py` dosyasıdır; `--factory`, başlangıç betiği veya Docker gerekmez. Komut Render'ın [FastAPI dağıtım düzenini](https://render.com/docs/deploy-fastapi) kullanır.

4. Kalıcı disk ekleyin: Mount Path **`/data`**, örneğin 1 GB.
5. Aşağıdaki ortam değişkenlerini girin. `PUBLIC_BASE_URL` için Render'ın verdiği gerçek HTTPS adresini kullanın; yol veya sondaki slash eklemeyin.

```dotenv
ADMIN_PASSWORD=Bilkent.yeni123
PUBLIC_BASE_URL=https://SIZIN-SERVISINIZ.onrender.com
DATABASE_URL=sqlite:////data/exam.db
COOKIE_SECURE=true
PORT=10000
FORWARDED_ALLOW_IPS=*
PYTHON_VERSION=3.11.13
```

Render'da `FORWARDED_ALLOW_IPS=*`, uygulamaya yalnızca Render'ın ters proxy katmanından erişildiği dağıtım içindir. Doğrudan internete açık farklı bir sunucuda `*` yerine güvenilen proxy IP adresini yazın. Yayına çıkarken yönetici şifresini kendi güçlü şifrenizle değiştirin.

`PUBLIC_BASE_URL` tanımlanmazsa Render’ın `RENDER_EXTERNAL_URL` değeri kullanılır. Özel alan adında `PUBLIC_BASE_URL` değerini o HTTPS adresine ayarlayın. Hazır değişken listesi `.env.render.example` dosyasındadır.

6. Manuel deploy başlatın. Migration'lar **uygulama başlangıcında**, disk bağlıyken çalışır. Render diskleri build/pre-deploy aşamasında erişilebilir olmadığından migration'ları bu aşamalara taşımayın.
7. `/healthz`, admin girişi, QR'ın gerçek URL'si ve iki cihazla bağlantıyı kontrol edin. HTTPS sayfalarda istemci otomatik `wss://` kullanır.

Render port ve Blueprint yapılandırmaları: [Web servisleri](https://render.com/docs/web-services), [Blueprint YAML](https://render.com/docs/blueprint-spec).

### İsteğe bağlı yerel Docker

```bash
docker build -t bilkent-live-exam .
docker volume create bilkent-exam-data
docker run --rm --name bilkent-exam -p 8000:10000 \
  --env-file .env \
  -e PORT=10000 -e DATABASE_URL=sqlite:////data/exam.db \
  -v bilkent-exam-data:/data bilkent-live-exam
```

`.env` içindeki `PUBLIC_BASE_URL=http://localhost:8000` yerel Docker erişimiyle eşleşmelidir.

## Migration, yedekleme ve geri yükleme

`migrations/001_initial.sql`, `002_session_requests.sql`, `003_question_context.sql` ve `004_session_duration.sql`, `005_participant_experience.sql` ve `006_question_images.sql` sıralı çalışır. Görsel migration’ı mevcut soru ve cevapları değiştirmeden görsel tablosunu ekler. `schema_migrations` tablosu uygulanan dosyaları izler; her dosya ve kayıt makbuzu aynı transaction'da commit edilir. Yeniden başlatma veya deploy mevcut tabloları silmez. Süre migration’ı mevcut oturumları ve cevapları korur, eski oturumlara 45 saniye varsayılanı ekler. Yeni şema değişiklikleri için yeni numaralı dosya ekleyin; uygulanmış migration'ları değiştirmeyin.

Çalışan SQLite'ı düz `cp` ile yedeklemeyin; WAL dosyaları nedeniyle eksik yedek oluşabilir. Dahili komut SQLite backup API'sini kullanır:

```bash
source .venv/bin/activate
python -m scripts.database backup backups/exam-2026-09-09.db
```

Yedek dosyası zaten varsa üzerine yazılmaz. Render Shell'de, konteynerin Python ortamıyla:

```bash
python -m scripts.database backup /data/backups/exam-2026-09-09.db
```

Yedekleri ayrıca disk/servis dışında güvenli bir yere alın. Yedekler katılımcı cevapları ve oturum token hash'leri içerir. Render Shell'den indirmek için yerel bilgisayarda ve Render Shell'de `magic-wormhole` kurulabilir; Render Shell'de `wormhole send /data/backups/exam-2026-09-09.db`, yerelde `wormhole receive <verilen-kod>` kullanılır. Yalnızca güvenilen tarafla kodu paylaşın.

Geri yükleme **sunucu durdurulduktan sonra** yapılır. Yerelde önce `Ctrl+C`, sonra:

```bash
python -m scripts.database restore backups/exam-2026-09-09.db --server-stopped
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Komut yedeğin bütünlüğünü doğrular, mevcut veritabanını `exam-before-restore-*.db` olarak yedekler ve restore eder. `--server-stopped` süreci kendisi durdurmaz; durdurma sorumluluğu operatördedir.

Render'da bakım geri yüklemesi için önce yedeği `/data/backups/restore.db` yoluna aktarın; **Start Command** değerini geçici olarak aşağıdaki yapın ve manuel deploy edin:

```bash
python -m scripts.database restore /data/backups/restore.db --server-stopped && exec uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers
```

Tek instance/disk modelinde eski instance durduktan sonra yeni instance başlangıcında restore çalışır. Başarılı restore sonrası **Start Command değerini hemen normal `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers` komutuna geri alın**; aksi hâlde sonraki yeniden başlatmada aynı yedek tekrar yüklenir. İşlem sırasında bakım kesintisi olur.

## Testler

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt -c constraints.txt
python -m pytest -q
python tests/browser_flow.py
```

Docker kurulumu varsa imajı oluşturup kalıcı disk/yeniden başlatma testini de çalıştırabilirsiniz:

```bash
docker build -t bilkent-live-exam:local .
python tests/docker_smoke.py
```

Bu test `127.0.0.1:8012` portunu, geçici bir konteyneri ve yalnızca kendisinin oluşturduğu diski kullanır; sonunda ikisini de kaldırır.

Tarayıcı testi varsayılan olarak kurulu Google Chrome'u başlatır. Chrome yoksa:

```bash
python -m playwright install chromium
BROWSER_CHANNEL=chromium python tests/browser_flow.py
```

Tarayıcı testi `127.0.0.1:8011` üzerinde geçici SQLite ile çalışır; normal `data/exam.db` dosyasını değiştirmez. Gerçek DOCX yüklenir, 10 soru önizlenip kaydedilir; QR görseli çözülerek katılım bağlantısı açılır. İki ayrı tarayıcı bağlamında mobil katılım, takma ad çakışması, eşzamanlı başlangıç, yenileme, ağ kesintisi, sonuçlar ve kişisel özet doğrulanır. **İlk soru gerçek 45 saniye beklenir**; kalan sorularda yalnızca test veritabanının bitiş zamanları ilerletilir. Ekran görüntüleri `test-results/` altında üretilir.

API testleri ayrıca 2–5 şık, bozuk dosyanın atomik reddi, dosya/ZIP/XML sınırları, yetki/CSRF/WebSocket izolasyonu, yinelenen cevap ve yönetici kontrolleri, kesin 45 saniye sınırı, restart/reconnect, erken cevap sızıntısı, geçmiş cevaplar ve dağılımı kapsar. Bu testler bir tıbbi içerik doğrulaması veya kapasite testi değildir.
