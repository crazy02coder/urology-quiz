import {$, api, authorize, showError, escape as e, letter} from './common.js';
const admin = location.pathname.startsWith('/admin/');
const sid = location.pathname.split('/').filter(Boolean).at(-1);
const base = admin ? `/api/admin/sessions/${sid}` : `/api/sessions/${sid}`;
const stage = $('#stage');
let durationDraft = null;
let current, signature='', socket, online=false, retry=0, stopped=false, pending=false, anchor=0, remaining=0, fitFrame;
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
  document.querySelectorAll('[data-choice]').forEach(button => { button.disabled = !online || pending || seconds===0 || current?.own_choice != null; });
  document.querySelectorAll('[data-control]').forEach(button => {button.disabled = !online || pending;});
}
setInterval(updateTimer,100);
function scheduleQuestionFit() {
  cancelAnimationFrame(fitFrame);
  fitFrame = requestAnimationFrame(fitProjectorQuestion);
}
function fitProjectorQuestion() {
  if (!['question', 'results'].includes(current?.phase)) return;
  const panel = stage.querySelector('.question-panel');
  const question = panel?.querySelector('.question-text');
  const options = panel ? [...panel.querySelectorAll('.option')] : [];
  if (!panel || !question || !options.length) return;
  const results = current.phase === 'results';
  const detailText = panel.querySelectorAll('.explanation p, .distribution h3, .distribution .badge');
  let questionSize = results ? Math.min(44, Math.max(23, innerWidth / 44)) : Math.min(64, Math.max(27, innerWidth / 28));
  let optionSize = results ? Math.min(25, Math.max(15, innerWidth / 74)) : Math.min(34, Math.max(17, innerWidth / 58));
  let detailSize = results ? 14 : 15;
  const applySizes = () => {
    question.style.fontSize = `${questionSize}px`;
    options.forEach(option => { option.style.fontSize = `${optionSize}px`; });
    detailText.forEach(element => { element.style.fontSize = `${detailSize}px`; });
  };
  const overflows = () => stage.scrollHeight > stage.clientHeight + 1 ||
    panel.scrollHeight > panel.clientHeight + 1 ||
    options.some(option => option.scrollHeight > option.clientHeight + 1);
  applySizes();
  document.body.classList.remove('stage-tight');
  while (overflows() && (questionSize > 15 || optionSize > 12 || detailSize > 10)) {
    questionSize = Math.max(15, questionSize - 1);
    optionSize = Math.max(12, optionSize - .5);
    detailSize = Math.max(10, detailSize - .25);
    applySizes();
  }
  document.body.classList.toggle('stage-tight', overflows());
}
window.addEventListener('resize', scheduleQuestionFit);
function apply(state) {
  const durationFocused = document.activeElement?.id === 'question-duration';
  if(state.phase !== 'lobby') durationDraft = null;
  document.body.classList.toggle('projector-question', ['question', 'results'].includes(state.phase));
  if (!['question', 'results'].includes(state.phase)) document.body.classList.remove('stage-tight');
  current=state; remaining=state.remaining_seconds || 0; anchor=performance.now();
  const {server_now, remaining_seconds, ...stable} = state;
  const next=JSON.stringify(stable);
  if (signature!==next) {signature=next; render(); scheduleQuestionFit(); if(durationFocused) $('#question-duration')?.focus({preventScroll:true});}
  updateTimer();
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
      showError(new Error(admin?'Yönetici girişiniz sona erdi. Eğitimler bağlantısından yeniden giriş yapın.':'Sınav katılımı doğrulanamadı. Sayfayı yenile.')); return;
    }
    setTimeout(connect,Math.min(10000,500*2**retry++));
  };
}
window.addEventListener('pagehide',()=>{stopped=true;socket?.close();});
window.addEventListener('offline',()=>{connection(false);socket?.close();});
window.addEventListener('pageshow',event=>{if(event.persisted) location.reload();});
function title() {return `<div class="session-heading"><div><span class="eyebrow">CANLI EĞİTİM ${!admin&&current.nickname?`· ${e(current.nickname)}`:''}</span><h1>${e(current.title)}</h1></div><span class="badge">${current.participant_count ?? 0} katılımcı</span></div>`;}
function render() {
  if(!admin && !current.joined) {
    connection(false,current.phase==='lobby'?'Katılım açık':'Katılım kapalı');
    stage.innerHTML=`<section class="card join-card"><span class="eyebrow">SINAVA KATIL</span><h1>${e(current.title)}</h1>${current.phase==='lobby'?'<p class="muted">Sınav boyunca seni bu adla tanıyacağız.</p><form id="join-form"><label for="nickname">Takma adın</label><input id="nickname" placeholder="Örn. user1" minlength="2" maxlength="30" autocomplete="nickname" required><button class="primary full">Sınava katıl →</button></form>':'<p>Bu sınav başladı veya tamamlandı. Yeni katılımcı alınmıyor.</p><p class="muted">Daha önce katıldıysan aynı tarayıcı ve cihazdan bağlantıyı aç.</p>'}</section>`;
    return;
  }
  if(current.phase==='lobby') {
    stage.innerHTML=title()+(admin?`<div class="lobby-grid"><section class="card qr-card"><span class="eyebrow">KATILMAK İÇİN QR KODU OKUTUN</span><img class="qr" src="${base}/qr.png" alt="Bu canlı sınava katılım QR kodu"><div class="qr-actions"><a class="button secondary" href="${base}/qr.png" download="bilkent-katilim.png">PNG indir ↓</a><button id="copy" class="secondary">Bağlantıyı kopyala</button></div><label class="sr-only" for="join-url">Katılım bağlantısı</label><input id="join-url" class="link-input" value="${e(current.join_url)}" readonly></section><section class="card lobby-people"><div class="section-heading"><h2>Katılımcılar</h2><span class="count">${current.participant_count}</span></div><p class="muted">Herkes katıldığında sınavı başlatın.</p><div class="names">${current.participants.map(name=>`<span class="name-chip">${e(name)}</span>`).join('')||'<p class="empty-people">İlk katılımcı bekleniyor…</p>'}</div><div class="lobby-bottom"><label for="question-duration">Her soru için süre (saniye)</label><input id="question-duration" type="number" min="5" max="300" step="1" required value="${e(durationDraft ?? current.question_duration_seconds)}" aria-describedby="duration-note"><p id="duration-note" class="footnote">5–300 saniye. Seçilen süre tüm sorulara uygulanır.<br>Başlattıktan sonra süre değiştirilemez ve yeni katılımcı alınmaz.</p><button class="primary full" data-control="start">Sınavı başlat →</button></div></section></div>`:`<section class="card waiting centered"><span class="waiting-dot" aria-hidden="true"></span><span class="eyebrow">HAZIRSIN, ${e(current.nickname)}</span><h2>Yöneticinin sınavı başlatması<br>bekleniyor</h2><p class="muted">İlk soru başladığında burada görünecek.</p><span class="badge">Süreyi yönetici belirler</span></section>`);
  } else if(current.phase==='question'||current.phase==='results') {
    const q=current.question, results=current.phase==='results';
    stage.innerHTML=title()+`<section class="question-panel ${results?'results-panel':'active-question-panel'}"><div class="question-meta"><span class="eyebrow">SORU ${current.question_index+1} / ${current.question_count}</span>${results?'<span class="badge">Cevaplama sona erdi</span>':'<div class="timer" role="timer" aria-label="Kalan saniye"><strong id="timer">—</strong><span>saniye</span></div>'}</div>${q.topic?`<p class="topic">${e(q.topic)}</p>`:""}<h2 class="question-text">${e(q.text)}</h2><div class="options">${q.options.map((option,i)=>results?`<div class="option result-option ${q.correct===i?'correct':'incorrect'}"><span class="letter">${letter(i)}</span><div class="grow">${e(option)}<small>${q.correct===i?'✓ Doğru cevap':'✕'}${current.own_choice===i?' · Senin cevabın':''}</small></div><span class="result-count">${current.distribution[i]}<small>cevap</small></span></div>`:admin?`<div class="option"><span class="letter">${letter(i)}</span><span>${e(option)}</span></div>`:`<button class="option ${current.own_choice===i?'selected':''}" data-choice="${i}" ${current.own_choice!=null?'disabled':''}><span class="letter">${letter(i)}</span><span>${e(option)}</span>${current.own_choice===i?'<span class="selected-mark">✓</span>':''}</button>`).join('')}</div>${results?chart():`<p class="answer-status" role="status">${!admin&&current.own_choice!=null?'✓ Cevabın kaydedildi, sonuçlar bekleniyor':admin?'Cevaplar alınıyor. Seçilen süre dolunca sonuçlar açılacak.':'Cevabını seç. Kaydettikten sonra değiştiremezsin.'}</p>`}</section>`;
    if(results) stage.insertAdjacentHTML('beforeend',`<div class="stage-bottom"><p class="muted">${admin?'Sonuçları değerlendirin; hazır olduğunuzda devam edin.':'Yöneticinin devam etmesi bekleniyor.'}</p>${admin?`<button class="primary" data-control="${current.question_index+1===current.question_count?'finish':'next'}">${current.question_index+1===current.question_count?'Sınavı bitir':'Sonraki soru →'}</button>`:''}</div>`);
  } else if(current.phase==='finished') {
    if(admin) { location.replace('/admin'); return; }
    stage.innerHTML=title()+`<section class="card completed centered"><span class="completion-icon" aria-hidden="true">✓</span><span class="eyebrow">SINAV TAMAMLANDI</span><h2>Katıldığın için teşekkürler</h2><p class="muted">İşte bu sınavdaki yanıtların.</p><div class="summary"><div><strong>${current.summary.correct}</strong><span>✓ Doğru</span></div><div><strong>${current.summary.wrong}</strong><span>✕ Yanlış</span></div><div><strong>${current.summary.blank}</strong><span>– Boş</span></div></div></section>`;
  }
}
function chart() {
  const max=Math.max(1,...current.distribution);
  return `<section class="distribution"><div class="section-heading"><h3>Yanıt dağılımı</h3><span class="badge neutral">${current.unanswered} kişi cevap vermedi</span></div><div class="bar-chart" role="img" aria-label="${e(current.distribution.map((n,i)=>`${letter(i)} şıkkı: ${n} kişi`).join(', '))}">${current.distribution.map((n,i)=>`<div class="chart-column ${current.question.correct===i?'chart-correct':'chart-incorrect'}"><strong>${n}</strong><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><rect x="12" y="${100-n/max*92}" width="76" height="${Math.max(1,n/max*92)}" rx="4"/></svg><span>${letter(i)} ${current.question.correct===i?'✓':''}</span></div>`).join('')}</div></section>`;
}
stage.addEventListener('submit',async event=>{
  if(event.target.id!=='join-form') return;
  event.preventDefault(); const button=event.submitter; button.disabled=true; showError(null);
  try {await api(`${base}/join`,{nickname:$('#nickname').value}); await refresh(); connect();}
  catch(error){showError(error);button.disabled=false;}
});
stage.addEventListener('input',event=>{
  if(event.target.id==='question-duration') durationDraft=event.target.value;
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
      if(answerButton) await api(`${base}/answers`,{question_id:current.question.id,choice:Number(answerButton.dataset.choice)});
      else await api(`${base}/control`,{action:controlButton.dataset.control,expected_version:current.version,...(duration!==undefined?{question_duration_seconds:duration}:{})});
      await refresh();
    } catch(error) {
      showError(new Error(answerButton?`Cevap işlemi tamamlanamadı: ${error.message}`:error.message));
      try {await refresh(); if(answerButton&&current.own_choice!=null) showError(null);} catch {}
    } finally {pending=false;updateTimer();}
  }
  if(event.target.closest('#copy')) {
    try {await navigator.clipboard.writeText(current.join_url);$('#copy').textContent='Kopyalandı ✓';}
    catch {$('#join-url').select();showError(new Error('Bağlantı otomatik kopyalanamadı. Seçili bağlantıyı kopyalayın.'));}
  }
});
try {if(admin) await authorize(); await refresh(); if(admin||current.joined) connect();}
catch(error){showError(error); connection(false,'Bağlantı kurulamadı · Sayfayı yenileyin');}
