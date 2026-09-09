# Doğrulama sonuçları

## Python ve Uvicorn dağıtım güncellemesi

Proje köküne taşındıktan sonra `main.py` ASGI giriş noktası ve Python runtime kullanan `render.yaml` hazırlandı. `python -m pytest -q`: **35 test geçti**. Ek testlerde proje başka adlı bir klasöre kopyalanıp farklı çalışma dizininden gerçek Uvicorn süreciyle açıldı; sağlık kontrolü, şablonlar, statik dosyalar, proje köküne göre SQLite yolu, `RENDER_EXTERNAL_URL` ve Secure yönetici çerezi doğrulandı. Render'a deploy yapılmadı. Aşağıdaki Docker sonuçları önceki sürümün test kayıtlarıdır.

9 Eylül 2026 · Python 3.11 · Yerel Chrome ve Docker

- `python -m pytest -q`: **33 test geçti**. Test istemcisinin bağımlılıklarından iki deprecation uyarısı var; başarısız test yok.
- Sağlanan DOCX: 10 soru, 4'er şık; cevap anahtarı **B C B D A A C D D A**. Gerçek yükleme, önizleme ve atomik kayıt doğrulandı. Ek DOCX testlerinde 2, 3 ve 5 şık doğrulandı.
- Dosya tipi/boyutu, boş soru/şık, eksik veya uyuşmayan doğru cevap, bozuk ZIP/XML, çoklu cevap ve eksik şık sırası reddedildi.
- QR PNG gerçek barkod çözücüsüyle okundu; çözülen bağlantı iki ayrı mobil tarayıcı bağlamında açıldı. Aynı takma adın reddi, Türkçe büyük/küçük harf eşleştirmesi ve oturum izolasyonu doğrulandı.
- İki katılımcı aynı soru ID'sini ve bitiş zamanını aldı. Tüm cevaplar erken verilse de soru açık kaldı. İlk soruda gerçek 45 saniye beklendi; tarayıcı sonuç ekranını 45,65 saniyede aldı. **Sunucu bitiş sınırı ayrıca tam 45,000 saniyede test edildi.** Görsel güncellemenin ağ/WebSocket gecikmesi cevap kabulünü uzatmaz.
- Süre dolunca eski/geç cevaplar reddedildi. Doğru cevap, ipucu, açıklama ve dağılım erken API/WebSocket çıktısında bulunmadı.
- Doğru/yanlış renkleri ve metinleri, dağılım, cevap vermeyen sayısı, yönetici ilerletmeden bekleme, 10 sorunun tamamlanması, kişisel özet ve geçmiş cevap tablosu doğrulandı.
- Yenileme, çevrimdışı kalıp yeniden bağlanma, yinelenen cevaplar, çift yönetici işlemi, yetkisiz API/WebSocket ve CSRF/origin kontrolleri geçti. Çıkış açık yönetici WebSocket yetkisini iptal etti.
- 390 px mobil ve 1440 px masaüstü ekran görüntüleri incelendi. 320 px genişlikte büyütülmüş metin kontrolü ve hareket azaltma tercihi doğrulandı. Tarayıcı testinde JavaScript/CSP hatası görülmedi.
- Docker imajı oluşturuldu. Ayrı test diskiyle `/data` altında SQLite, gerçek DOCX yükleme, konteyner yeniden başlatma sonrası aynı bitiş zamanı/cevap/çerezler, WebSocket yeniden bağlantısı ve yedekleme doğrulandı. Test konteyneri ve diski kaldırıldı.
- Migration'lar tekrarlı çalıştırıldı; kayıtları silmedi. SQLite backup API yedeği ve yedeğin iki kez geri yüklenmesi (önceki veritabanının koruma yedeği dahil) test edildi.
- `pip check`: bağımlılık çakışması yok. JavaScript dosyalarının sözdizimi kontrolü geçti.

Yerel uygulama veritabanında yalnızca sağlanan 10 soruluk sınav hazırlandı; tarayıcı ve Docker testleri ayrı geçici veritabanlarında çalıştı. Kaynak DOCX değiştirilmedi. Render yapılandırması ve Türkçe kurulum/backup/restore açıklamaları hazırlandı; Render'a deploy yapılmadı. Fiziksel telefon kamerası, hastane ağı, yüksek katılımcı yükü ve tıbbi içerik doğruluğu bu yazılım testlerinin kapsamı dışındadır.
