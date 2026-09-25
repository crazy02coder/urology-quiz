import {$, api, authorize, showError, escape as e, letter, toast, stagger, countUp, growBars, date,
        copyText, initTheme, initAccordion} from './common.js';
const admin = location.pathname.startsWith('/admin/');
const sid = location.pathname.split('/').filter(Boolean).at(-1);
const base = admin ? `/api/admin/sessions/${sid}` : `/api/sessions/${sid}`;
const stage = $('#stage');
let durationDraft = null;
let current, signature='', socket, online=false, retry=0, stopped=false, pending=false, anchor=0, remaining=0;
let detailsState = 'idle', answerToasted = -1;
let reviewData = null, reviewAnchor = null, reviewBusy = false;
$('#back').hidden = !admin;
document.body.classList.toggle('projector', admin);
function connection(connected, message) {
  online=connected; $('#connection').textContent=message || (connected?'● Canlı bağlantı':'Bağlantı kesildi · Yeniden bağlanılıyor…');
  $('#connection').classList.toggle('disconnected', !connected);
  updateTimer();
}
function updateTimer() {
  const seconds = Math.max(0, Math.ceil(remaining - (performance.now()-anchor)/1000));
  const timer = $('#timer');
  if(timer) {timer.textContent=seconds; timer.closest('.timer').classList.toggle('urgent',seconds<=10);}
  document.querySelectorAll('[data-choice]').forEach(button => { button.disabled = !online || pending || seconds===0; });
  document.querySelectorAll('[data-control]').forEach(button => {button.disabled = !online || pending;});
}
setInterval(updateTimer,100);
initAccordion(stage);
initTheme();
// Fit only the reading area; charts never force question text to shrink.
// Live questions may grow a little into spare space; results keep their compact scale.
let quizFitFrame=0;
function scheduleQuizFit() {
  cancelAnimationFrame(quizFitFrame);
  quizFitFrame=requestAnimationFrame(fitQuizCore);
}
function prepareQuizImages(core, available, mobile) {
  const galleries=[...core.querySelectorAll('.question-images')];
  if(!galleries.length) return null;
  let rows=0;
  galleries.forEach(gallery=>{
    const count=gallery.querySelectorAll('.question-image').length;
    const columns=Math.min(count,mobile?3:4,Math.max(1,Math.floor(gallery.clientWidth/(mobile?100:160))));
    gallery.style.setProperty('--quiz-image-columns',String(columns));
    rows+=Math.ceil(count/columns);
  });
  // Both question and explanation galleries share the image budget.
  // Caption lines, row gaps and gallery margins are included in it.
  const spacing=rows*18+(rows-galleries.length)*6+galleries.length*12;
  const min=mobile?44:64;
  const max=Math.max(min,Math.min(mobile?150:220,Math.floor((available*.3-spacing)/rows)));
  core.style.setProperty('--quiz-image-height',`${max}px`);
  return {min,max};
}
function shrinkQuizImages(core, sizes, available) {
  if(!sizes || core.offsetHeight<=available) return;
  let lower=sizes.min, upper=sizes.max;
  core.style.setProperty('--quiz-image-height',`${lower}px`);
  if(core.offsetHeight>available) return;
  for(let step=0;step<7;step++) {
    const size=(lower+upper)/2;
    core.style.setProperty('--quiz-image-height',`${size}px`);
    if(core.offsetHeight<=available) lower=size;
    else upper=size;
  }
  core.style.setProperty('--quiz-image-height',`${Math.floor(lower)}px`);
}
function fitQuizCore() {
  const core=stage.querySelector('.quiz-core');
  if(!core || !document.body.classList.contains('projector-question')) return;
  core.style.setProperty('--quiz-scale','1');
  core.style.removeProperty('--quiz-live-height');
  core.style.removeProperty('--quiz-image-height');
  core.classList.remove('quiz-compact');
  const livePanel=core.closest('.live-panel');
  const height=window.visualViewport?.height || window.innerHeight;
  const liveFooter=stage.querySelector('.live-bottom');
  const footerSpace=liveFooter?liveFooter.offsetHeight+8:0;
  const bottomSpace=livePanel
    ? parseFloat(getComputedStyle(livePanel).paddingBottom)+parseFloat(getComputedStyle($('#session-main')).paddingBottom)+10
    : 16;
  const available=height-(core.getBoundingClientRect().top+window.scrollY)-footerSpace-bottomSpace;
  const mobile=window.matchMedia('(max-width:650px)').matches;
  const imageSizes=prepareQuizImages(core,Math.max(0,available),mobile);
  if(livePanel && available>0 && core.offsetHeight<=available) {
    let lower=1, upper=mobile?1.15:1.18;
    core.style.setProperty('--quiz-scale',String(upper));
    if(core.offsetHeight<=available) lower=upper;
    else {
      for(let step=0;step<7;step++) {
        const scale=(lower+upper)/2;
        core.style.setProperty('--quiz-scale',String(scale));
        if(core.offsetHeight<=available) lower=scale;
        else upper=scale;
      }
    }
    core.style.setProperty('--quiz-scale',String(Math.floor(lower*1000)/1000));
    core.style.setProperty('--quiz-live-height',`${Math.floor(available)}px`);
    return;
  }
  if(available<=0 || core.offsetHeight<=available) return;
  core.classList.add('quiz-compact');
  shrinkQuizImages(core,imageSizes,available);
  if(core.offsetHeight<=available) {
    if(livePanel) core.style.setProperty('--quiz-live-height',`${Math.floor(available)}px`);
    return;
  }
  const limits=[['.question-text',mobile?15:20],['.opt-text',mobile?14:16],['.explanation p',mobile?12:13]];
  let lower=Math.min(1,...limits.map(([selector,min])=>{
    const element=core.querySelector(selector);
    return element?min/parseFloat(getComputedStyle(element).fontSize):1;
  }));
  let upper=1;
  core.style.setProperty('--quiz-scale',String(lower));
  // Unusually long content remains accessible in normal page flow.
  if(core.offsetHeight>available) return;
  for(let step=0;step<7;step++) {
    const scale=(lower+upper)/2;
    core.style.setProperty('--quiz-scale',String(scale));
    if(core.offsetHeight<=available) lower=scale;
    else upper=scale;
  }
  core.style.setProperty('--quiz-scale',String(Math.floor(lower*1000)/1000));
  if(livePanel) core.style.setProperty('--quiz-live-height',`${Math.floor(available)}px`);
}
window.addEventListener('resize',scheduleQuizFit);
window.visualViewport?.addEventListener('resize',scheduleQuizFit);
document.fonts?.ready.then(scheduleQuizFit);
stage.addEventListener('load',event=>{
  if(event.target.matches('.question-image img')) scheduleQuizFit();
},true);
function apply(state) {
  const durationFocused = document.activeElement?.id === 'question-duration';
  if(state.phase !== 'lobby') durationDraft = null;
  document.body.classList.toggle('projector-question', ['question', 'results'].includes(state.phase));
  document.body.classList.toggle('phase-results', state.phase === 'results');
  if (state.phase !== 'finished') detailsState = 'idle';
  current=state; remaining=state.remaining_seconds || 0; anchor=performance.now();
  // Yönetici soruyu ilerletirse inceleme modu kendiliğinden kapanır.
  if(reviewData && (state.question_index!==reviewAnchor || state.phase==='question')) reviewData=null;
  const {server_now, remaining_seconds, answered_count, ...stable} = state;
  const next=JSON.stringify(stable)+(reviewData?`|review${reviewData.question_index}`:'');
  if (signature!==next) {signature=next; render(); decorate(); if(durationFocused) $('#question-duration')?.focus({preventScroll:true});}
  updateTimer(); updateMeter();
}
async function refresh() {apply(await api(base));}
function connect() {
  if(stopped) return;
  socket = new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws/${admin?'admin':'participant'}/${sid}`);
  let lastMessage=performance.now();
  const watchdog=setInterval(()=>{if(performance.now()-lastMessage>5000) socket.close();},1000);
  socket.onmessage=event=>{
    if(!navigator.onLine) return;
    lastMessage=performance.now(); retry=0; connection(true);
    apply(JSON.parse(event.data));
  };
  socket.onerror=()=>connection(false);
  socket.onclose=event=>{
    clearInterval(watchdog); connection(false);
    if(stopped) return;
    if(event.code===4401 || event.code===4403) {
      stopped=true; connection(false,'Sınav doğrulanamadı · Sayfayı yenileyin');
      const message=admin?'Yönetici girişiniz sona erdi. Eğitimler bağlantısından yeniden giriş yapın.':'Sınav katılımı doğrulanamadı. Sayfayı yenile.';
      showError(new Error(message)); toast(message,'error',0); return;
    }
    setTimeout(connect,Math.min(10000,500*2**retry++));
  };
}
window.addEventListener('pagehide',()=>{stopped=true;socket?.close();});
window.addEventListener('offline',()=>{connection(false);socket?.close();});
window.addEventListener('pageshow',event=>{if(event.persisted) location.reload();});
function title() {return `<div class="session-heading"><div><span class="eyebrow">CANLI EĞİTİM ${!admin&&current.nickname?`· ${e(current.nickname)}`:''}</span><h1>${e(current.title)}</h1></div><span class="badge">${current.participant_count ?? 0} katılımcı</span></div>`;}
function render() {
  document.body.classList.toggle('question-has-images', Boolean((reviewData || current)?.question?.images?.length));
  if(reviewData) {stage.innerHTML=title()+resultsPanel(reviewData,true); return;}
  if(!admin && !current.joined && current.phase==='finished') {
    connection(false,'Bağlantının süresi doldu');
    stage.innerHTML=`<section class="card link-state-card"><div class="logo-orbit" aria-hidden="true"><span class="logo-ring"></span><img class="logo-spin" src="/static/img/saglik-bakanligi.png" alt=""></div><span class="eyebrow">BAĞLANTININ SÜRESİ DOLDU</span><h1>Bu eğitim sona erdi</h1><p class="muted">Okuttuğunuz QR kodu tamamlanmış bir eğitime ait; yeni katılım alınmıyor.</p><p class="link-state-hint"><strong>Aktif eğitim bağlantısına bağlanmayı deneyin.</strong> Eğitmeninizin ekranındaki güncel QR kodunu yeniden okutun.</p></section>`;
    return;
  }
  if(!admin && !current.joined) {
    connection(false,current.phase==='lobby'?'Katılım açık':'Katılım kapalı');
    stage.innerHTML=`<section class="card join-card"><span class="eyebrow">SINAVA KATIL</span><h1>${e(current.title)}</h1>${current.phase==='lobby'?'<p class="muted">Sınav boyunca seni bu adla tanıyacağız.</p><form id="join-form"><label for="nickname">Takma adın</label><input id="nickname" placeholder="Örn. user1" minlength="2" maxlength="30" autocomplete="nickname" required><label for="experience">Kaç yıldır bu alanda çalışıyorsun?</label><input id="experience" type="number" min="0" max="60" step="1" value="0" inputmode="numeric" required aria-describedby="experience-note"><p id="experience-note" class="footnote">Yeni başladıysan <strong>0</strong> yaz. Sonuçlar deneyim yılına göre de karşılaştırılır.</p><button class="primary full">Sınava katıl →</button></form>':'<p>Bu sınav başladı veya tamamlandı. Yeni katılımcı alınmıyor.</p><p class="muted">Daha önce katıldıysan aynı tarayıcı ve cihazdan bağlantıyı aç.</p>'}</section>`;
    return;
  }
  if(current.phase==='lobby') {
    stage.innerHTML=title()+(admin?`<div class="lobby-grid"><section class="card qr-card"><span class="eyebrow">KATILMAK İÇİN QR KODU OKUTUN</span><img class="qr" src="${base}/qr.png" alt="Bu canlı sınava katılım QR kodu"><div class="qr-actions"><a class="button secondary" href="${base}/qr.png" download="bilkent-katilim.png">PNG indir ↓</a><button id="copy" class="secondary">Bağlantıyı kopyala</button></div><label class="sr-only" for="join-url">Katılım bağlantısı</label><input id="join-url" class="link-input" value="${e(current.join_url)}" readonly></section><section class="card lobby-people"><div class="section-heading"><h2>Katılımcılar</h2><span class="count">${current.participant_count}</span></div><p class="muted">Herkes katıldığında sınavı başlatın.</p><div class="names">${current.participants.map(person=>`<span class="name-chip">${e(person.nickname)}<small>${person.experience_years} yıl</small></span>`).join('')||'<p class="empty-people">İlk katılımcı bekleniyor…</p>'}</div><div class="lobby-bottom"><label for="question-duration">Her soru için süre (saniye)</label><input id="question-duration" type="number" min="5" max="300" step="1" required value="${e(durationDraft ?? current.question_duration_seconds)}" aria-describedby="duration-note"><p id="duration-note" class="footnote">5–300 saniye. Seçilen süre tüm sorulara uygulanır.<br>Başlattıktan sonra süre değiştirilemez ve yeni katılımcı alınmaz.</p><button class="primary full" data-control="start">Sınavı başlat →</button></div></section></div>`:`<section class="card waiting centered"><span class="waiting-dot" aria-hidden="true"></span><span class="eyebrow">HAZIRSIN, ${e(current.nickname)}</span><h2>Yöneticinin sınavı başlatması<br>bekleniyor</h2><p class="muted">İlk soru başladığında burada görünecek.</p><span class="badge">Süreyi yönetici belirler</span></section>`);
  } else if(current.phase==='question'||current.phase==='results') {
    if(current.phase==='results') stage.innerHTML=title()+resultsPanel(current);
    else stage.innerHTML=title()+livePanel(current)+liveBar();
  } else if(current.phase==='finished') {
    if(admin) {
      stage.innerHTML=title()+`<section class="card completed centered finished-head"><span class="completion-icon" aria-hidden="true">✓</span><span class="eyebrow">SINAV TAMAMLANDI</span><h2>Oturum sonuçları</h2><p class="muted">Aşağıdaki döküm bu oturuma özeldir ve kayıtlıdır; bu bağlantıdan tekrar açabilirsiniz.</p></section><div id="finished-details" class="details-slot"><p class="loading-line">İstatistikler hazırlanıyor…</p></div>`;
    } else {
      stage.innerHTML=title()+`<section class="card completed centered finished-head"><span class="completion-icon" aria-hidden="true">✓</span><span class="eyebrow">SINAV TAMAMLANDI</span><h2>Katıldığın için teşekkürler</h2><p class="muted">İşte bu sınavdaki yanıtların.</p><div class="summary"><div><strong data-count="${current.summary.correct}">0</strong><span>✓ Doğru</span></div><div><strong data-count="${current.summary.wrong}">0</strong><span>✕ Yanlış</span></div><div><strong data-count="${current.summary.blank}">0</strong><span>– Boş</span></div></div></section><div id="finished-details" class="details-slot"><p class="loading-line">Cevap dökümün hazırlanıyor…</p></div>`;
    }
    loadFinishedDetails();
  }
}
function chart(v=current) {
  return `<section class="quiz-chart option-chart" aria-label="Şık oranları">
    <div class="quiz-chart-heading"><div><h3>Şık oranları</h3><p>Tüm katılımcılara göre cevap dağılımı</p></div><span class="badge neutral">${v.unanswered} kişi cevap vermedi</span></div>
    <div class="option-plot"><div class="option-plot-axis" aria-hidden="true"><span>100%</span><span>50%</span><span>0%</span></div><div class="option-plot-bars">${v.distribution.map((n,i)=>{
    const right=v.question.correct===i;
    const percent=Math.round(100*n/(v.participant_count||1));
    return `<div class="option-plot-column ${right?'is-correct':'is-incorrect'}" aria-label="${letter(i)} şıkkı: ${n} kişi, yüzde ${percent}${right?', doğru cevap':''}"><div class="option-plot-track"><span class="option-plot-fill" data-percent="${percent}"></span></div><strong>${letter(i)}${right?' ✓':''}</strong><span class="option-plot-value">${percent}% <small>· ${n} kişi</small></span></div>`;
  }).join('')}</div></div></section>`;
}
function imageUrl(id) {
  return `/api/sessions/${encodeURIComponent(sid)}/images/${encodeURIComponent(id)}`;
}
function questionPictures(q, placement='question') {
  const images=(q?.images||[]).filter(image=>image.placement===placement);
  if(!images.length) return '';
  const label=placement==='explanation'?'Açıklama görseli':'Soru görseli';
  return `<div class="question-images">${images.map((image,i)=>{
    const url=imageUrl(image.id);
    return `<figure class="question-image"><a href="${url}" target="_blank" rel="noopener noreferrer" aria-label="${label} ${i+1} · Tam boy aç" title="Görseli tam boy aç"><img src="${url}" alt="${label} ${i+1}" loading="lazy"></a><figcaption>Büyüt ↗</figcaption></figure>`;
  }).join('')}</div>`;
}
function explanation(v=current) {
  const q=v.question;
  const pictures=questionPictures(q, 'explanation');
  return q.explanation||q.hint||pictures?`<section class="explanation"><h3>Açıklama</h3>${q.explanation?`<p>${e(q.explanation)}</p>`:''}${q.hint?`<p class="muted">İpucu: ${e(q.hint)}</p>`:''}${pictures}</section>`:'';
}
function bar(percent) {
  return `<span class="exp-track"><span class="exp-fill" data-percent="${Number(percent)||0}"></span></span>`;
}
function experienceChart(v=current) {
  const groups=v.experience||[];
  if(!groups.length) return '';
  return `<section class="quiz-chart experience-chart" aria-label="Deneyim yılına göre başarı">
    <div class="quiz-chart-heading"><div><h3>Deneyim yılına göre başarı</h3><p>Her deneyim grubunda doğru cevap verenlerin oranı</p></div><span class="badge neutral">${groups.length} deneyim grubu</span></div>
    <div class="experience-plot-scale" aria-hidden="true"><span>0%</span><span>50%</span><span>100%</span></div>
    <ul class="experience-plot">${groups.map(g=>{
        const percent=Math.min(100,Math.max(0,Number(g.percent)||0));
        return `<li class="experience-plot-row ${perf(percent)}"><div class="experience-plot-label"><strong>${e(g.label)}</strong><small>${g.correct} / ${g.total} doğru</small></div><span class="exp-track" aria-hidden="true"><span class="exp-fill" data-percent="${percent}"></span></span><strong class="experience-plot-value">${percent}%</strong></li>`;
      }).join('')}</ul>
  </section>`;
}
function livePanel(v) { return questionPanel(v, false); }
function resultsPanel(v, isReview=false) { return questionPanel(v, true, isReview); }
function questionPanel(v, revealed, isReview=false) {
  const q=v.question;
  const share=n=>Math.round(100*n/(v.participant_count||1));
  const status=revealed
    ? `<span class="badge">${v.answered_count ?? 0} / ${v.participant_count} yanıtladı</span>`
    : '<div class="timer" role="timer" aria-label="Kalan saniye"><strong id="timer">—</strong><span>saniye</span></div>';
  const options=q.options.map((option,i)=>{
    const interactive=!revealed&&!admin;
    const tag=interactive?'button':'div';
    const n=revealed?v.distribution[i]:0, pct=share(n);
    const right=revealed&&q.correct===i, mine=v.own_choice===i;
    const state=revealed?`result-option ${right?'correct':'incorrect'}${mine?' picked':''}`:mine?'selected':'';
    const note=revealed?[right?'✓ Doğru cevap':'',mine?'Senin cevabın':''].filter(Boolean).join(' · '):mine?'✓ Seçimin · süre bitene kadar değiştirebilirsin':'';
    // Empty note/count slots keep option text aligned between the two phases.
    // Correct answers and result data are rendered only after revelation.
    return `<${tag} class="option ${state}" ${interactive?`type="button" data-choice="${i}"`:''}>
      ${revealed?`<span class="opt-fill" data-percent="${pct}"></span>`:''}
      <span class="letter">${letter(i)}</span>
      <div class="grow"><span class="opt-text">${e(option)}</span><small class="option-note" ${note?'':'aria-hidden="true"'}>${note||'&nbsp;'}</small></div>
      ${revealed?`<span class="result-count"><strong>${n}</strong><small>${pct}%</small></span>`:'<span class="option-count-space" aria-hidden="true"></span>'}
    </${tag}>`;
  }).join('');
  return `<section class="question-panel results-panel quiz-panel${revealed?'':' live-panel'}">
    <div class="quiz-core">
    <div class="question-meta"><span class="eyebrow">SORU ${v.question_index+1} / ${v.question_count}</span>${status}</div>
    ${q.topic?`<p class="topic">${e(q.topic)}</p>`:''}
    <h2 class="question-text">${e(q.text)}</h2>${questionPictures(q)}
    <div class="options">${options}</div>
    ${revealed?`${reviewBar(v,isReview)}${explanation(v)}`:''}
    </div>
    ${revealed?`<div class="result-analytics">${chart(v)}${experienceChart(v)}</div>`:''}
  </section>`;
}
function liveBar() {
  const status=!admin&&current.own_choice!=null?'✓ Cevabın kaydedildi. Süre bitene kadar değiştirebilirsin.':admin?'Cevaplar alınıyor. Süre dolunca sonuçlar açılacak.':'Cevabını seç. Süre bitene kadar değiştirebilirsin.';
  return `<div class="stage-bottom live-bottom">${answerMeter()}<p class="muted answer-status" role="status">${status}</p></div>`;
}
function reviewBar(v, isReview) {
  const max=current.revealed_max ?? -1;
  const index=v.question_index;
  const back=index>0, forward=index<max;
  const advance=!isReview&&admin&&current.phase==='results';
  return `<div class="stage-bottom review-controls${admin?' is-admin':''}"><div class="review-nav">${isReview?`<span class="review-flag">İnceleme · Soru ${index+1} / ${v.question_count}</span>`:''}<button type="button" class="secondary" data-review="${index-1}" ${back?'':'disabled'}>← Önceki soru</button>${isReview?`<button type="button" class="secondary" data-review="${index+1}" ${forward?'':'disabled'}>Sonraki soru →</button><button type="button" class="secondary" data-review="live">Canlıya dön ↺</button>`:''}</div><p class="muted">${isReview?'Bu soru salt okunur — cevaplar kapalı.':admin?'Sonuçları değerlendirin; hazır olduğunuzda devam edin.':'Yöneticinin devam etmesi bekleniyor.'}</p>${advance?`<button class="primary" data-control="${current.question_index+1===current.question_count?'finish':'next'}">${current.question_index+1===current.question_count?'Sınavı bitir':'Sonraki soru →'}</button>`:''}</div>`;
}
async function openReview(index) {
  if(reviewBusy) return;
  reviewBusy=true;
  try {
    const data=await api(`/api/sessions/${sid}/questions/${index}`);
    reviewData=data; reviewAnchor=current.question_index;
    signature=''; render(); decorate();
  } catch(error) {toast(error.message,'error');}
  finally {reviewBusy=false;}
}
function exitReview() {
  reviewData=null; signature=''; render(); decorate();
}
function decorate(root=stage) {
  stagger(root.querySelectorAll('.options>.option, .exp-row, .stat-tile, .name-chip, .stat-question, .rev-question'));
  root.querySelectorAll('[data-count]').forEach(element=>countUp(element,Number(element.dataset.count),{suffix:element.dataset.suffix||''}));
  growBars(root);
  scheduleQuizFit();
}
function perf(percent) {
  return percent>=60?'perf-high':percent>=30?'perf-mid':'perf-low';
}
function adminStats(d) {
  return `<section class="stat-row">
    <div class="stat-tile"><span class="stat-label">Katılımcı</span><strong data-count="${d.participant_count}">0</strong></div>
    <div class="stat-tile"><span class="stat-label">Soru</span><strong data-count="${d.question_count}">0</strong></div>
    <div class="stat-tile"><span class="stat-label">Ortalama doğru</span><strong data-count="${d.average_correct}">0</strong><small>/ ${d.question_count} soru</small></div>
    <div class="stat-tile accent"><span class="stat-label">Genel başarı</span><strong data-count="${d.average_percent}" data-suffix="%">0</strong><small>${d.total_correct} doğru cevap</small></div>
  </section>`;
}

/* ===== Sonuç gezgini =======================================================
   Tek kaynak: /history (kişi × soru cevap matrisi). Filtre uygulandığında soru
   ve yıl istatistikleri yalnızca seçili kişiler üzerinden yeniden hesaplanır. */
let ex = null;
const EX_SORTS = {
  people:    [['percent','Başarı'],['correct','Doğru sayısı'],['years','Deneyim yılı'],['nickname','Takma ad']],
  questions: [['position','Soru sırası'],['percent','Başarı'],['correct','Doğru sayısı']],
  years:     [['percent','Grup içi başarı'],['correct','Grup içi doğru sayısı']],
};
const fold = value => String(value).toLocaleLowerCase('tr');
function scoreOf(person, questions) {
  let correct=0, wrong=0, blank=0;
  questions.forEach(q=>{const a=person.answers[q.id]; if(a==null) blank++; else if(a===q.correct) correct++; else wrong++;});
  return {correct, wrong, blank, percent: questions.length?Math.round(100*correct/questions.length):0};
}
function exPeople() {
  const term=fold(ex.search.trim());
  return ex.data.participants.filter(person =>
    (!ex.years.size || ex.years.has(person.experience_years)) &&
    (!term || fold(person.nickname).includes(term)));
}
function exSort(rows) {
  const {key, dir} = ex.sort;
  return rows.sort((a,b)=>{
    const x=a.sort[key], y=b.sort[key];
    const diff = typeof x==='string' ? x.localeCompare(y,'tr') : x-y;
    return (diff||0)*dir || String(a.sort.label).localeCompare(String(b.sort.label),'tr');
  });
}
function exEmpty(message) {
  return `<div class="empty small-empty">${e(message)}</div>`;
}
function answerRow(person, q) {
  const a=person.answers[q.id];
  const status=a==null?'blank':a===q.correct?'correct':'wrong';
  return `<li class="ans ans-${status}"><span class="ans-no">${q.position+1}</span><div class="grow"><p class="ans-q">${e(q.text)}</p><p class="ans-given">${a==null?'– Boş bıraktı':`<strong>${letter(a)}</strong> · ${e(q.options[a])}`}</p>${status==='correct'?'':`<p class="ans-right">✓ Doğru cevap: <strong>${letter(q.correct)}</strong> · ${e(q.options[q.correct])}</p>`}</div><span class="ans-mark" aria-hidden="true">${status==='correct'?'✓':status==='wrong'?'✕':'–'}</span></li>`;
}
function exBodyPeople() {
  const questions=ex.data.questions;
  const rows=exSort(exPeople().map(person=>{
    const score=scoreOf(person,questions);
    return {person, score, sort:{percent:score.percent, correct:score.correct, years:person.experience_years, nickname:person.nickname, label:person.nickname}};
  }));
  if(!rows.length) return exEmpty('Bu filtreye uyan katılımcı yok.');
  return `<div class="acc-list">${rows.map(({person,score},i)=>{
    const chips=`<span class="acc-score"><span class="pill pill-ok">${score.correct} ✓</span><span class="pill pill-bad">${score.wrong} ✕</span><span class="pill">${score.blank} –</span></span>`;
    const inner=`<ul class="acc-answers">${questions.map(q=>answerRow(person,q)).join('')}</ul>`;
    return accordion(`ex-p${i}`,`<span class="rank">${i+1}</span>${e(person.nickname)}`,`${person.experience_years} yıl deneyim`,chips,score.percent,inner);
  }).join('')}</div>`;
}
function questionStats(q, people) {
  const counts=new Array(q.options.length).fill(0);
  let blank=0;
  const byYear=new Map();
  people.forEach(person=>{
    const a=person.answers[q.id];
    const entry=byYear.get(person.experience_years) || {years:person.experience_years, total:0, correct:0};
    entry.total++;
    if(a==null || a<0 || a>=counts.length) blank++;
    else {counts[a]++; if(a===q.correct) entry.correct++;}
    byYear.set(person.experience_years, entry);
  });
  const correct=counts[q.correct]||0;
  const years=[...byYear.values()].sort((a,b)=>a.years-b.years)
    .map(entry=>({...entry, percent: entry.total?Math.round(100*entry.correct/entry.total):0}));
  return {counts, blank, correct, percent: people.length?Math.round(100*correct/people.length):0, years};
}
function exBodyQuestions() {
  const people=exPeople();
  if(!people.length) return exEmpty('Bu filtreye uyan katılımcı yok, soru istatistiği hesaplanamıyor.');
  const rows=exSort(ex.data.questions.map(q=>{
    const stats=questionStats(q,people);
    return {q, stats, sort:{position:q.position, percent:stats.percent, correct:stats.correct, label:q.position}};
  }));
  return `<div class="acc-list">${rows.map(({q,stats},i)=>{
    const chips=`<span class="acc-score"><span class="pill pill-ok">${stats.correct} ✓</span><span class="pill pill-bad">${people.length-stats.correct-stats.blank} ✕</span><span class="pill">${stats.blank} –</span></span>`;
    const inner=`<div class="q-detail">${q.topic?`<p class="topic">${e(q.topic)}</p>`:''}<p class="q-full">${e(q.text)}</p>${questionPictures(q)}<ul class="stat-options">${q.options.map((option,j)=>`<li class="${q.correct===j?'is-correct':''}"><span class="letter">${letter(j)}</span><span class="grow">${e(option)}</span><span class="stat-count">${stats.counts[j]}</span></li>`).join('')}<li class="is-blank"><span class="letter">–</span><span class="grow">Boş bırakan</span><span class="stat-count">${stats.blank}</span></li></ul>${stats.years.length?`<h4 class="sub-heading">Deneyim yılına göre</h4><div class="exp-rows">${stats.years.map(y=>`<div class="exp-row"><span class="exp-label">${y.years} yıl</span>${bar(y.percent)}<span class="exp-value"><strong>${y.percent}%</strong><small>${y.correct}/${y.total}</small></span></div>`).join('')}</div>`:''}${q.explanation||q.hint||(q.images||[]).some(image=>image.placement==='explanation')?accordion(`ex-n${i}`,'İpucu ve açıklama','','',null,`<div class="note-body">${q.explanation?`<p>${e(q.explanation)}</p>`:''}${q.hint?`<p class="muted"><strong>İpucu:</strong> ${e(q.hint)}</p>`:''}${questionPictures(q,'explanation')}</div>`,'acc-quiet'):''}</div>`;
    return accordion(`ex-q${i}`,`<span class="rank">${q.position+1}</span>${e(q.text.slice(0,90))}${q.text.length>90?'…':''}`,`✓ ${letter(q.correct)} · ${e(q.options[q.correct])}`,chips,stats.percent,inner);
  }).join('')}</div>`;
}
function exBodyYears() {
  const questions=ex.data.questions;
  const people=exPeople();
  if(!people.length) return exEmpty('Bu filtreye uyan katılımcı yok.');
  const map=new Map();
  people.forEach(person=>{
    const entry=map.get(person.experience_years) || {years:person.experience_years, members:[]};
    entry.members.push({person, score:scoreOf(person,questions)});
    map.set(person.experience_years, entry);
  });
  // Year groups stay in chronological order; the controls sort their members.
  const rows=[...map.values()].sort((a,b)=>a.years-b.years).map(entry=>{
    entry.members=exSort(entry.members.map(member=>({
      ...member,
      sort:{percent:member.score.percent, correct:member.score.correct, label:member.person.nickname},
    })));
    const correct=entry.members.reduce((sum,m)=>sum+m.score.correct,0);
    const total=entry.members.length*questions.length;
    const percent=total?Math.round(100*correct/total):0;
    return {entry, correct, total, percent};
  });
  return `<div class="acc-list">${rows.map(({entry,correct,total,percent},i)=>{
    const chips=`<span class="acc-score"><span class="pill">${entry.members.length} kişi</span><span class="pill pill-ok">${correct}/${total} doğru</span></span>`;
    const ranked=`<ol class="rank-list">${entry.members.map((m,j)=>`<li class="rank-row ${perf(m.score.percent)}"><span class="ans-no">${j+1}</span><span class="grow"><strong>${e(m.person.nickname)}</strong><small>${m.score.correct} doğru · ${m.score.wrong} yanlış · ${m.score.blank} boş</small></span>${bar(m.score.percent)}<span class="ans-pct"><strong>${m.score.percent}%</strong></span></li>`).join('')}</ol>`;
    const perQuestion=`<h4 class="sub-heading">Bu yılın soru soru başarısı</h4><ul class="acc-answers">${questions.map(q=>{
      const hit=entry.members.filter(m=>m.person.answers[q.id]===q.correct).length;
      const pct=entry.members.length?Math.round(100*hit/entry.members.length):0;
      return `<li class="ans ${perf(pct)}"><span class="ans-no">${q.position+1}</span><div class="grow"><p class="ans-q">${e(q.text)}</p><span class="exp-track ans-bar"><span class="exp-fill" data-percent="${pct}"></span></span></div><span class="ans-pct"><strong>${pct}%</strong><small>${hit}/${entry.members.length}</small></span></li>`;
    }).join('')}</ul>`;
    return accordion(`ex-y${i}`,`${entry.years} yıl deneyim`,'',chips,percent,`<div class="q-detail"><h4 class="sub-heading">Sıralama</h4>${ranked}${perQuestion}</div>`);
  }).join('')}</div>`;
}
function explorerShell(data) {
  const years=[...new Set(data.participants.map(person=>person.experience_years))].sort((a,b)=>a-b);
  const tabs=[['people','Kişiler'],['questions','Sorular'],['years','Deneyim yılları']];
  return `<section class="card stats-card explorer"><div class="section-heading"><h2>Sonuç gezgini</h2><span class="count" id="ex-count">${data.participants.length}</span></div>
    <div class="ex-tabs" role="tablist" aria-label="Sonuç görünümü">${tabs.map(([id,label])=>`<button type="button" role="tab" class="ex-tab" data-extab="${id}" aria-selected="${id==='people'}">${label}</button>`).join('')}</div>
    <div class="ex-bar"><div class="ex-field ex-search"><span class="ex-icon" aria-hidden="true">⌕</span><label class="sr-only" for="ex-search">Takma ad ara</label><input id="ex-search" type="search" placeholder="Takma ad ara…" autocomplete="off"></div><div class="ex-field ex-select"><span class="ex-field-label" aria-hidden="true">Sırala</span><label class="sr-only" for="ex-sort">Sıralama ölçütü</label><select id="ex-sort"></select></div><button type="button" id="ex-dir" class="ex-button"><span class="ex-dir-icon" aria-hidden="true">↓</span><span id="ex-dir-text">Yüksekten</span></button><button type="button" id="ex-reset" class="ex-button ex-reset">Temizle</button></div>
    ${years.length>1?`<div class="ex-years" role="group" aria-label="Deneyim yılı filtresi"><span class="ex-years-label">Deneyim yılı:</span>${years.map(y=>`<button type="button" class="year-chip" data-exyear="${y}" aria-pressed="false">${y} yıl</button>`).join('')}</div>`:''}
    <p class="ex-summary" id="ex-summary" role="status"></p><div id="ex-body"></div></section>`;
}
function exSyncSort() {
  const select=$('#ex-sort');
  const options=EX_SORTS[ex.tab];
  if(!options.some(([key])=>key===ex.sort.key)) ex.sort.key=options[0][0];
  select.innerHTML=options.map(([key,label])=>`<option value="${key}" ${key===ex.sort.key?'selected':''}>${label}</option>`).join('');
  const down=ex.sort.dir<0;
  $('#ex-dir-text').textContent=down?'Yüksekten':'Düşükten';
  $('.ex-dir-icon').textContent=down?'↓':'↑';
  $('#ex-dir').setAttribute('aria-label',down?'Şu an yüksekten düşüğe sıralı; düşükten yükseğe çevir':'Şu an düşükten yükseğe sıralı; yüksekten düşüğe çevir');
  $('#ex-dir').title=$('#ex-dir').getAttribute('aria-label');
}
function exRender() {
  const body=$('#ex-body');
  if(!body) return;
  document.querySelectorAll('[data-extab]').forEach(tab=>tab.setAttribute('aria-selected',String(tab.dataset.extab===ex.tab)));
  document.querySelectorAll('[data-exyear]').forEach(chip=>chip.setAttribute('aria-pressed',String(ex.years.has(Number(chip.dataset.exyear)))));
  const shown=exPeople().length, total=ex.data.participants.length;
  const filtered=shown!==total;
  $('#ex-count').textContent=shown;
  $('#ex-summary').textContent=filtered
    ? `${total} katılımcıdan ${shown} tanesi gösteriliyor. Soru ve yıl istatistikleri bu seçime göre hesaplandı.`
    : `${total} katılımcının tamamı gösteriliyor.`;
  $('#ex-summary').classList.toggle('is-filtered', filtered);
  body.innerHTML=ex.tab==='people'?exBodyPeople():ex.tab==='questions'?exBodyQuestions():exBodyYears();
  decorate(body);
}
function reviewQuestion(q,i,groupLabel) {
  const status=q.own_choice==null?'blank':q.own_choice===q.correct?'correct':'wrong';
  const label={correct:'✓ Doğru bildin',wrong:'✕ Yanlış',blank:'– Boş bıraktın'}[status];
  return `<article class="rev-question rev-${status}"><div class="stat-question-head"><span class="eyebrow">SORU ${i+1}</span><span class="rev-badge">${label}</span></div>${q.topic?`<p class="topic">${e(q.topic)}</p>`:''}<h3>${e(q.text)}</h3>${questionPictures(q)}<ul class="stat-options">${q.options.map((o,j)=>`<li class="${q.correct===j?'is-correct':''}${q.own_choice===j&&q.correct!==j?' is-picked':''}"><span class="letter">${letter(j)}</span><span class="grow">${e(o)}</span><span class="rev-mark">${q.correct===j?'✓ Doğru cevap':q.own_choice===j?'Senin cevabın':''}</span></li>`).join('')}</ul>${q.group_total>1?`<p class="rev-peer">${e(groupLabel)} grubundaki ${q.group_total} kişiden ${q.group_correct} kişi doğru bildi <strong>(${q.group_percent}%)</strong></p>`:''}${explanation({question:q})}</article>`;
}
function participantReview(d) {
  const above=d.percent>=d.group_average_percent;
  return `<section class="stat-row">
    <div class="stat-tile accent"><span class="stat-label">Başarın</span><strong data-count="${d.percent}" data-suffix="%">0</strong><small>${d.summary.correct}/${d.questions.length} doğru</small></div>
    <div class="stat-tile"><span class="stat-label">${e(d.experience_group)} ortalaması</span><strong data-count="${d.group_average_percent}" data-suffix="%">0</strong><small>${d.group_size} kişi</small></div>
    <div class="stat-tile"><span class="stat-label">Deneyimin</span><strong data-count="${d.experience_years}">0</strong><small>yıl</small></div>
  </section>
  <p class="notice ${above?'notice-good':''}">${above?'Kendi deneyim grubunun ortalamasında veya üzerindesin.':'Kendi deneyim grubunun ortalamasının altındasın. Aşağıdaki açıklamalar yardımcı olabilir.'}</p>
  <section class="card stats-card"><div class="section-heading"><h2>Cevap dökümün</h2><span class="count">${d.questions.length}</span></div><div class="rev-list">${d.questions.map((q,i)=>reviewQuestion(q,i,d.experience_group)).join('')}</div></section>`;
}
function answerMeter() {
  const total=current.participant_count||0, answered=current.answered_count??0;
  const percent=total?Math.round(100*answered/total):0;
  return `<div class="answer-meter"><div class="meter-head"><span class="meter-count"><strong>${answered}</strong> / ${total} kişi yanıtladı</span><span class="meter-percent">${percent}%</span></div><span class="exp-track"><span class="exp-fill" data-percent="${percent}"></span></span></div>`;
}
function updateMeter() {
  const meter=stage.querySelector('.answer-meter');
  if(!meter||!current) return;
  const total=current.participant_count||0, answered=current.answered_count??0;
  const percent=total?Math.round(100*answered/total):0;
  meter.querySelector('.meter-count').innerHTML=`<strong>${answered}</strong> / ${total} kişi yanıtladı`;
  meter.querySelector('.meter-percent').textContent=`${percent}%`;
  meter.querySelector('.exp-fill').style.setProperty('--fill',`${percent}%`);
}
function accordion(id,title,meta,score,percent,inner,cls='') {
  return `<div class="acc ${cls}"><button type="button" class="acc-head" data-acc aria-expanded="false" aria-controls="${id}"><span class="acc-caret" aria-hidden="true">›</span><span class="acc-title"><strong>${title}</strong>${meta?`<small>${meta}</small>`:''}</span>${score}${percent===null?'':`<span class="acc-percent"><span class="exp-track"><span class="exp-fill" data-percent="${percent}"></span></span><strong>${percent}%</strong></span>`}</button><div class="acc-panel" id="${id}"><div class="acc-inner">${inner}</div></div></div>`;
}
async function loadFinishedDetails() {
  if(detailsState!=='idle') return;
  detailsState='loading';
  const slot=$('#finished-details');
  try {
    if(admin) {
      const [stats, history]=await Promise.all([api(`${base}/stats`), api(`${base}/history`)]);
      if(!slot.isConnected) {detailsState='idle'; return;}
      slot.innerHTML=adminStats(stats)+explorerShell(history);
      ex={data:history, search:'', years:new Set(), tab:'people', sort:{key:'percent', dir:-1}};
      detailsState='done';
      exSyncSort(); exRender(); decorate(slot);
    } else {
      const data=await api(`${base}/review`);
      if(!slot.isConnected) {detailsState='idle'; return;}
      slot.innerHTML=participantReview(data);
      detailsState='done';
      decorate(slot);
    }
  } catch(error) {
    detailsState='idle';
    slot.innerHTML='<p class="loading-line">Döküm yüklenemedi. <button type="button" class="text-button" id="retry-details">Yeniden dene</button></p>';
    toast(error.message,'error');
  }
}
stage.addEventListener('error', event => {
  if (!event.target.matches('.question-image img')) return;
  event.target.alt = 'Görsel yüklenemedi; büyüt bağlantısıyla yeniden açın.';
  scheduleQuizFit();
}, true);
stage.addEventListener('submit',async event=>{
  if(event.target.id!=='join-form') return;
  event.preventDefault(); const button=event.submitter; button.disabled=true; showError(null);
  const experience=$('#experience');
  if(!experience.reportValidity()||!Number.isInteger(experience.valueAsNumber)) {
    button.disabled=false; toast('Deneyim yılını 0 ile 60 arasında bir tam sayı olarak gir.','warn'); return;
  }
  try {
    await api(`${base}/join`,{nickname:$('#nickname').value, experience_years:experience.valueAsNumber});
    await refresh(); connect(); toast(`Hoş geldin ${current.nickname}! Sınavın başlaması bekleniyor.`,'success');
  }
  catch(error){showError(error);toast(error.message,'error');button.disabled=false;}
});
stage.addEventListener('input',event=>{
  if(event.target.id==='question-duration') durationDraft=event.target.value;
  if(event.target.id==='ex-search' && ex) {ex.search=event.target.value; exRender();}
});
stage.addEventListener('change',event=>{
  if(event.target.id==='ex-sort' && ex) {ex.sort.key=event.target.value; exRender();}
});
stage.addEventListener('click',async event=>{
  const answerButton=event.target.closest('[data-choice]'), controlButton=event.target.closest('[data-control]');
  if(answerButton||controlButton) {
    if(pending||!online) return;
    const durationInput = controlButton?.dataset.control === 'start' ? $('#question-duration') : null;
    if(durationInput && !durationInput.reportValidity()) return;
    const duration = durationInput ? durationInput.valueAsNumber : undefined;
    pending=true; updateTimer(); showError(null);
    try {
      if(answerButton) {
        const result=await api(`${base}/answers`,{question_id:current.question.id,choice:Number(answerButton.dataset.choice)});
        if(result.changed) toast('Cevabın güncellendi.','success',2200);
        else if(answerToasted!==current.question_index) {answerToasted=current.question_index; toast('Cevabın kaydedildi. Süre bitene kadar değiştirebilirsin.','success');}
      }
      else await api(`${base}/control`,{action:controlButton.dataset.control,expected_version:current.version,...(duration!==undefined?{question_duration_seconds:duration}:{})});
      await refresh();
    } catch(error) {
      showError(new Error(answerButton?`Cevap işlemi tamamlanamadı: ${error.message}`:error.message));
      toast(error.message,'error');
      try {await refresh(); if(answerButton&&current.own_choice!=null) showError(null);} catch {}
    } finally {pending=false;updateTimer();}
  }
  if(event.target.closest('#copy')) {
    const copied=await copyText(current.join_url,$('#join-url'));
    if(copied) {$('#copy').textContent='Kopyalandı ✓'; showError(null); toast('Katılım bağlantısı kopyalandı.','success');}
    else {$('#join-url').select(); showError(new Error('Bağlantı otomatik kopyalanamadı. Seçili bağlantıyı kopyalayın.')); toast('Tarayıcı kopyalamaya izin vermedi; seçili bağlantıyı elle kopyalayın.','warn');}
  }
  if(event.target.closest('#retry-details')) {detailsState='idle'; $('#finished-details').innerHTML='<p class="loading-line">Yeniden deneniyor…</p>'; loadFinishedDetails(); return;}
  const reviewButton=event.target.closest('[data-review]');
  if(reviewButton) {
    if(reviewButton.disabled) return;
    const value=reviewButton.dataset.review;
    if(value==='live') exitReview(); else await openReview(Number(value));
    return;
  }
  if(!ex) return;
  const tab=event.target.closest('[data-extab]');
  if(tab) {ex.tab=tab.dataset.extab; exSyncSort(); exRender(); return;}
  const chip=event.target.closest('[data-exyear]');
  if(chip) {
    const year=Number(chip.dataset.exyear);
    ex.years.has(year)?ex.years.delete(year):ex.years.add(year);
    exRender(); return;
  }
  if(event.target.closest('#ex-dir')) {ex.sort.dir*=-1; exSyncSort(); exRender(); return;}
  if(event.target.closest('#ex-reset')) {
    ex.search=''; ex.years.clear(); $('#ex-search').value='';
    exRender(); toast('Filtreler temizlendi.','info',2200); return;
  }
});
try {if(admin) await authorize(); await refresh(); if(admin||current.joined) connect();}
catch(error){showError(error); connection(false,'Bağlantı kurulamadı · Sayfayı yenileyin');}
