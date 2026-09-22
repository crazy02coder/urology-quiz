import {$, api, authorize, showError, escape as e, letter, toast, stagger, countUp, growBars, date,
        copyText, initTheme, initAccordion} from './common.js';
const admin = location.pathname.startsWith('/admin/');
const sid = location.pathname.split('/').filter(Boolean).at(-1);
const base = admin ? `/api/admin/sessions/${sid}` : `/api/sessions/${sid}`;
const stage = $('#stage');
let durationDraft = null;
let current, signature='', socket, online=false, retry=0, stopped=false, pending=false, anchor=0, remaining=0, fitFrame;
let detailsState = 'idle', answerToasted = -1;
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
initAccordion(stage);
initTheme();
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
  const detailText = panel.querySelectorAll('.explanation p, .distribution h3, .distribution .badge, .experience-panel .exp-label, .experience-panel .exp-value');
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
  document.body.classList.toggle('phase-results', state.phase === 'results');
  if (state.phase !== 'finished') detailsState = 'idle';
  if (!['question', 'results'].includes(state.phase)) document.body.classList.remove('stage-tight');
  current=state; remaining=state.remaining_seconds || 0; anchor=performance.now();
  const {server_now, remaining_seconds, answered_count, ...stable} = state;
  const next=JSON.stringify(stable);
  if (signature!==next) {signature=next; render(); decorate(); scheduleQuestionFit(); if(durationFocused) $('#question-duration')?.focus({preventScroll:true});}
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
  if(!admin && !current.joined) {
    connection(false,current.phase==='lobby'?'Katılım açık':'Katılım kapalı');
    stage.innerHTML=`<section class="card join-card"><span class="eyebrow">SINAVA KATIL</span><h1>${e(current.title)}</h1>${current.phase==='lobby'?'<p class="muted">Sınav boyunca seni bu adla tanıyacağız.</p><form id="join-form"><label for="nickname">Takma adın</label><input id="nickname" placeholder="Örn. user1" minlength="2" maxlength="30" autocomplete="nickname" required><label for="experience">Kaç yıldır bu alanda çalışıyorsun?</label><input id="experience" type="number" min="0" max="60" step="1" value="0" inputmode="numeric" required aria-describedby="experience-note"><p id="experience-note" class="footnote">Yeni başladıysan <strong>0</strong> yaz. Sonuçlar deneyim yılına göre de karşılaştırılır.</p><button class="primary full">Sınava katıl →</button></form>':'<p>Bu sınav başladı veya tamamlandı. Yeni katılımcı alınmıyor.</p><p class="muted">Daha önce katıldıysan aynı tarayıcı ve cihazdan bağlantıyı aç.</p>'}</section>`;
    return;
  }
  if(current.phase==='lobby') {
    stage.innerHTML=title()+(admin?`<div class="lobby-grid"><section class="card qr-card"><span class="eyebrow">KATILMAK İÇİN QR KODU OKUTUN</span><img class="qr" src="${base}/qr.png" alt="Bu canlı sınava katılım QR kodu"><div class="qr-actions"><a class="button secondary" href="${base}/qr.png" download="bilkent-katilim.png">PNG indir ↓</a><button id="copy" class="secondary">Bağlantıyı kopyala</button></div><label class="sr-only" for="join-url">Katılım bağlantısı</label><input id="join-url" class="link-input" value="${e(current.join_url)}" readonly></section><section class="card lobby-people"><div class="section-heading"><h2>Katılımcılar</h2><span class="count">${current.participant_count}</span></div><p class="muted">Herkes katıldığında sınavı başlatın.</p><div class="names">${current.participants.map(person=>`<span class="name-chip">${e(person.nickname)}<small>${person.experience_years} yıl</small></span>`).join('')||'<p class="empty-people">İlk katılımcı bekleniyor…</p>'}</div><div class="lobby-bottom"><label for="question-duration">Her soru için süre (saniye)</label><input id="question-duration" type="number" min="5" max="300" step="1" required value="${e(durationDraft ?? current.question_duration_seconds)}" aria-describedby="duration-note"><p id="duration-note" class="footnote">5–300 saniye. Seçilen süre tüm sorulara uygulanır.<br>Başlattıktan sonra süre değiştirilemez ve yeni katılımcı alınmaz.</p><button class="primary full" data-control="start">Sınavı başlat →</button></div></section></div>`:`<section class="card waiting centered"><span class="waiting-dot" aria-hidden="true"></span><span class="eyebrow">HAZIRSIN, ${e(current.nickname)}</span><h2>Yöneticinin sınavı başlatması<br>bekleniyor</h2><p class="muted">İlk soru başladığında burada görünecek.</p><span class="badge">Süreyi yönetici belirler</span></section>`);
  } else if(current.phase==='question'||current.phase==='results') {
    const q=current.question, results=current.phase==='results';
    stage.innerHTML=title()+`<section class="question-panel ${results?'results-panel':'active-question-panel'}"><div class="question-meta"><span class="eyebrow">SORU ${current.question_index+1} / ${current.question_count}</span>${results?`<span class="badge">${current.answered_count ?? 0} / ${current.participant_count} yanıtladı</span>`:'<div class="timer" role="timer" aria-label="Kalan saniye"><strong id="timer">—</strong><span>saniye</span></div>'}</div>${q.topic?`<p class="topic">${e(q.topic)}</p>`:""}<h2 class="question-text">${e(q.text)}</h2><div class="options">${q.options.map((option,i)=>results?`<div class="option result-option ${q.correct===i?'correct':'incorrect'}"><span class="letter">${letter(i)}</span><div class="grow">${e(option)}<small>${q.correct===i?'✓ Doğru cevap':'✕'}${current.own_choice===i?' · Senin cevabın':''}</small></div><span class="result-count">${current.distribution[i]}<small>cevap</small></span></div>`:admin?`<div class="option"><span class="letter">${letter(i)}</span><span>${e(option)}</span></div>`:`<button class="option ${current.own_choice===i?'selected':''}" data-choice="${i}" ${current.own_choice!=null?'disabled':''}><span class="letter">${letter(i)}</span><span>${e(option)}</span>${current.own_choice===i?'<span class="selected-mark">✓</span>':''}</button>`).join('')}</div>${results?chart()+experienceChart()+explanation():`${answerMeter()}<p class="answer-status" role="status">${!admin&&current.own_choice!=null?'✓ Cevabın kaydedildi, sonuçlar bekleniyor':admin?'Cevaplar alınıyor. Seçilen süre dolunca sonuçlar açılacak.':'Cevabını seç. Kaydettikten sonra değiştiremezsin.'}</p>`}</section>`;
    if(results) stage.insertAdjacentHTML('beforeend',`<div class="stage-bottom"><p class="muted">${admin?'Sonuçları değerlendirin; hazır olduğunuzda devam edin.':'Yöneticinin devam etmesi bekleniyor.'}</p>${admin?`<button class="primary" data-control="${current.question_index+1===current.question_count?'finish':'next'}">${current.question_index+1===current.question_count?'Sınavı bitir':'Sonraki soru →'}</button>`:''}</div>`);
  } else if(current.phase==='finished') {
    if(admin) {
      stage.innerHTML=title()+`<section class="card completed centered finished-head"><span class="completion-icon" aria-hidden="true">✓</span><span class="eyebrow">SINAV TAMAMLANDI</span><h2>Oturum sonuçları</h2><p class="muted">Aşağıdaki döküm bu oturuma özeldir ve kayıtlıdır; bu bağlantıdan tekrar açabilirsiniz.</p></section><div id="finished-details" class="details-slot"><p class="loading-line">İstatistikler hazırlanıyor…</p></div>`;
    } else {
      stage.innerHTML=title()+`<section class="card completed centered finished-head"><span class="completion-icon" aria-hidden="true">✓</span><span class="eyebrow">SINAV TAMAMLANDI</span><h2>Katıldığın için teşekkürler</h2><p class="muted">İşte bu sınavdaki yanıtların.</p><div class="summary"><div><strong data-count="${current.summary.correct}">0</strong><span>✓ Doğru</span></div><div><strong data-count="${current.summary.wrong}">0</strong><span>✕ Yanlış</span></div><div><strong data-count="${current.summary.blank}">0</strong><span>– Boş</span></div></div></section><div id="finished-details" class="details-slot"><p class="loading-line">Cevap dökümün hazırlanıyor…</p></div>`;
    }
    loadFinishedDetails();
  }
}
function chart() {
  const max=Math.max(1,...current.distribution);
  return `<section class="distribution"><div class="section-heading"><h3>Yanıt dağılımı</h3><span class="badge neutral">${current.unanswered} kişi cevap vermedi</span></div><div class="bar-chart" role="img" aria-label="${e(current.distribution.map((n,i)=>`${letter(i)} şıkkı: ${n} kişi`).join(', '))}">${current.distribution.map((n,i)=>`<div class="chart-column ${current.question.correct===i?'chart-correct':'chart-incorrect'}"><strong>${n}</strong><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><rect x="12" y="${100-n/max*92}" width="76" height="${Math.max(1,n/max*92)}" rx="4"/></svg><span>${letter(i)} ${current.question.correct===i?'✓':''}</span></div>`).join('')}</div></section>`;
}
function explanation() {
  const q=current.question;
  return q.explanation||q.hint?`<section class="explanation"><h3>Açıklama</h3>${q.explanation?`<p>${e(q.explanation)}</p>`:''}${q.hint?`<p class="muted">İpucu: ${e(q.hint)}</p>`:''}</section>`:'';
}
function bar(percent) {
  return `<span class="exp-track"><span class="exp-fill" data-percent="${Number(percent)||0}"></span></span>`;
}
function experienceChart() {
  const groups=current.experience||[];
  if(!groups.length) return '';
  return `<section class="experience-panel"><div class="section-heading"><h3>Deneyime göre doğru oranı</h3><span class="badge neutral">${groups.length} grup</span></div><div class="exp-rows">${groups.map(g=>`<div class="exp-row"><span class="exp-label">${e(g.label)}<small>${g.total} kişi</small></span>${bar(g.percent)}<span class="exp-value"><strong>${g.percent}%</strong><small>${g.correct}/${g.total}</small></span></div>`).join('')}</div></section>`;
}
function decorate(root=stage) {
  stagger(root.querySelectorAll('.options>.option, .exp-row, .stat-tile, .name-chip, .stat-question, .rev-question'));
  root.querySelectorAll('[data-count]').forEach(element=>countUp(element,Number(element.dataset.count),{suffix:element.dataset.suffix||''}));
  growBars(root);
}
function groupCard(heading, groups, note) {
  if(!groups?.length) return '';
  return `<section class="card stats-card"><div class="section-heading"><h2>${e(heading)}</h2><span class="count">${groups.length}</span></div><div class="exp-rows">${groups.map(g=>`<div class="exp-row"><span class="exp-label">${e(g.label)}<small>${g.participants} kişi</small></span>${bar(g.percent)}<span class="exp-value"><strong>${g.percent}%</strong><small>${g.correct}/${g.total}</small></span></div>`).join('')}</div>${note?`<p class="footnote">${e(note)}</p>`:''}</section>`;
}
function questionStat(q,i) {
  return `<article class="stat-question"><div class="stat-question-head"><span class="eyebrow">SORU ${i+1}</span><span class="badge ${q.percent>=60?'':'neutral'}">${q.percent}% doğru</span></div>${q.topic?`<p class="topic">${e(q.topic)}</p>`:''}<h3>${e(q.text)}</h3><div class="exp-track wide">${''}<span class="exp-fill" data-percent="${q.percent}"></span></div><ul class="stat-options">${q.options.map((o,j)=>`<li class="${q.correct===j?'is-correct':''}"><span class="letter">${letter(j)}</span><span class="grow">${e(o)}</span><span class="stat-count">${q.distribution[j]}</span></li>`).join('')}<li class="is-blank"><span class="letter">–</span><span class="grow">Boş bırakan</span><span class="stat-count">${q.unanswered}</span></li></ul>${q.groups.length?`<div class="mini-groups">${q.groups.map(g=>`<div class="mini-group"><span class="mini-label">${e(g.label)}</span>${bar(g.percent)}<span class="mini-value"><strong>${g.percent}%</strong><small>${g.correct}/${g.total}</small></span></div>`).join('')}</div>`:''}${q.hint||q.explanation?accordion(`acc-n${i}`,'İpucu ve açıklama','','',null,`<div class="note-body">${q.explanation?`<p>${e(q.explanation)}</p>`:''}${q.hint?`<p class="muted"><strong>İpucu:</strong> ${e(q.hint)}</p>`:''}</div>`,'acc-quiet'):''}</article>`;
}
function perf(percent) {
  return percent>=60?'perf-high':percent>=30?'perf-mid':'perf-low';
}
function groupQuestionSection(d) {
  if(!d.groups.length||!d.questions.length) return '';
  const items=d.groups.map((group,i)=>{
    const rows=d.questions.map(q=>({q, cell:q.groups.find(x=>x.label===group.label)})).filter(row=>row.cell);
    if(!rows.length) return '';
    const inner=`<ul class="acc-answers">${rows.map(({q,cell})=>`<li class="ans ${perf(cell.percent)}"><span class="ans-no">${q.position+1}</span><div class="grow"><p class="ans-q">${e(q.text)}</p><span class="exp-track ans-bar"><span class="exp-fill" data-percent="${cell.percent}"></span></span></div><span class="ans-pct"><strong>${cell.percent}%</strong><small>${cell.correct}/${cell.total}</small></span></li>`).join('')}</ul>`;
    const score=`<span class="acc-score"><span class="pill">${group.participants} kişi</span></span>`;
    return accordion(`acc-g${i}`,e(group.label),`${group.correct}/${group.total} doğru cevap`,score,group.percent,inner);
  }).join('');
  return `<section class="card stats-card"><div class="section-heading"><h2>Deneyim grubuna göre soru soru başarı</h2><span class="count">${d.groups.length}</span></div><p class="footnote acc-hint">Bir gruba dokunarak o grubun her sorudaki başarı oranını açın.</p><div class="acc-list">${items}</div></section>`;
}
function adminStats(d) {
  return `<section class="stat-row">
    <div class="stat-tile"><span class="stat-label">Katılımcı</span><strong data-count="${d.participant_count}">0</strong></div>
    <div class="stat-tile"><span class="stat-label">Soru</span><strong data-count="${d.question_count}">0</strong></div>
    <div class="stat-tile"><span class="stat-label">Ortalama doğru</span><strong data-count="${d.average_correct}">0</strong><small>/ ${d.question_count} soru</small></div>
    <div class="stat-tile accent"><span class="stat-label">Genel başarı</span><strong data-count="${d.average_percent}" data-suffix="%">0</strong><small>${d.total_correct} doğru cevap</small></div>
  </section>
  ${groupCard('Deneyime göre genel başarı', d.groups, 'Yüzdeler, gruptaki kişi sayısı × soru sayısı üzerinden hesaplanır; boş bırakılanlar yanlış sayılır.')}
  ${groupQuestionSection(d)}
  <section class="card stats-card"><div class="section-heading"><h2>Soru bazında başarı</h2><span class="count">${d.question_count}</span></div><div class="stat-questions">${d.questions.map(questionStat).join('')}</div></section>
  <section class="card stats-card"><div class="section-heading"><h2>Katılımcılar</h2><span class="count">${d.participant_count}</span></div><div class="table-scroll"><table><caption class="sr-only">Katılımcı başına sonuçlar</caption><thead><tr><th>Takma ad</th><th>Deneyim</th><th>✓ Doğru</th><th>✕ Yanlış</th><th>– Boş</th><th>Başarı</th></tr></thead><tbody>${d.participants.map(p=>`<tr><th>${e(p.nickname)}</th><td>${p.experience_years} yıl<small class="muted cell-sub">${e(p.experience_group)}</small></td><td>${p.correct}</td><td>${p.wrong}</td><td>${p.blank}</td><td><strong>${p.percent}%</strong></td></tr>`).join('')||'<tr><td colspan="6">Bu oturuma kimse katılmadı.</td></tr>'}</tbody></table></div><button id="history-button" class="secondary">Soru bazında cevap kayıtlarını göster</button><div id="history"></div></section>`;
}
function reviewQuestion(q,i,groupLabel) {
  const status=q.own_choice==null?'blank':q.own_choice===q.correct?'correct':'wrong';
  const label={correct:'✓ Doğru bildin',wrong:'✕ Yanlış',blank:'– Boş bıraktın'}[status];
  return `<article class="rev-question rev-${status}"><div class="stat-question-head"><span class="eyebrow">SORU ${i+1}</span><span class="rev-badge">${label}</span></div>${q.topic?`<p class="topic">${e(q.topic)}</p>`:''}<h3>${e(q.text)}</h3><ul class="stat-options">${q.options.map((o,j)=>`<li class="${q.correct===j?'is-correct':''}${q.own_choice===j&&q.correct!==j?' is-picked':''}"><span class="letter">${letter(j)}</span><span class="grow">${e(o)}</span><span class="rev-mark">${q.correct===j?'✓ Doğru cevap':q.own_choice===j?'Senin cevabın':''}</span></li>`).join('')}</ul>${q.group_total>1?`<p class="rev-peer">${e(groupLabel)} grubundaki ${q.group_total} kişiden ${q.group_correct} kişi doğru bildi <strong>(${q.group_percent}%)</strong></p>`:''}${q.explanation||q.hint?`<div class="explanation"><h3>Açıklama</h3>${q.explanation?`<p>${e(q.explanation)}</p>`:''}${q.hint?`<p class="muted">İpucu: ${e(q.hint)}</p>`:''}</div>`:''}</article>`;
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
function historyAccordion(data) {
  const rows=data.participants.map((person,i)=>{
    let correct=0,wrong=0,blank=0;
    data.questions.forEach(q=>{const a=person.answers[q.id]; if(a==null)blank++; else if(a===q.correct)correct++; else wrong++;});
    const percent=data.questions.length?Math.round(100*correct/data.questions.length):0;
    const score=`<span class="acc-score"><span class="pill pill-ok">${correct} ✓</span><span class="pill pill-bad">${wrong} ✕</span><span class="pill">${blank} –</span></span>`;
    const inner=`<ul class="acc-answers">${data.questions.map(q=>{
      const a=person.answers[q.id];
      const status=a==null?'blank':a===q.correct?'correct':'wrong';
      return `<li class="ans ans-${status}"><span class="ans-no">${q.position+1}</span><div class="grow"><p class="ans-q">${e(q.text)}</p><p class="ans-given">${a==null?'– Boş bıraktı':`<strong>${letter(a)}</strong> · ${e(q.options[a])}`}</p>${status==='correct'?'':`<p class="ans-right">✓ Doğru cevap: <strong>${letter(q.correct)}</strong> · ${e(q.options[q.correct])}</p>`}</div><span class="ans-mark" aria-hidden="true">${status==='correct'?'✓':status==='wrong'?'✕':'–'}</span></li>`;
    }).join('')}</ul>`;
    return accordion(`acc-p${i}`,e(person.nickname),`${person.experience_years} yıl · ${e(person.experience_group)}`,score,percent,inner);
  }).join('');
  const key=`<ul class="acc-answers">${data.questions.map(q=>`<li class="ans ans-correct"><span class="ans-no">${q.position+1}</span><div class="grow"><p class="ans-q">${e(q.text)}</p><p class="ans-right">✓ Doğru cevap: <strong>${letter(q.correct)}</strong> · ${e(q.options[q.correct])}</p></div></li>`).join('')}</ul>`;
  return `<div class="acc-list">${rows}${accordion('acc-key','Tüm soruların doğru cevapları',`${data.questions.length} soru`,'',null,key)}</div>`;
}
async function loadFinishedDetails() {
  if(detailsState!=='idle') return;
  detailsState='loading';
  const slot=$('#finished-details');
  try {
    const data=await api(admin?`${base}/stats`:`${base}/review`);
    if(!slot.isConnected) {detailsState='idle'; return;}
    slot.innerHTML=admin?adminStats(data):participantReview(data);
    detailsState='done';
    decorate(slot);
  } catch(error) {
    detailsState='idle';
    slot.innerHTML='<p class="loading-line">Döküm yüklenemedi. <button type="button" class="text-button" id="retry-details">Yeniden dene</button></p>';
    toast(error.message,'error');
  }
}
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
        await api(`${base}/answers`,{question_id:current.question.id,choice:Number(answerButton.dataset.choice)});
        if(answerToasted!==current.question_index) {answerToasted=current.question_index; toast('Cevabın kaydedildi. Sonuçlar süre bitince açılacak.','success');}
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
  const historyButton=event.target.closest('#history-button');
  if(historyButton) {
    historyButton.disabled=true;
    try {
      const data=await api(`${base}/history`);
      const slot=$('#history');
      slot.innerHTML=`<p class="footnote acc-hint">Bir katılımcıya dokunarak soru soru verdiği cevapları açın.</p>`+historyAccordion(data);
      historyButton.hidden=true;
      decorate(slot);
    } catch(error) {historyButton.disabled=false; toast(error.message,'error');}
  }
});
try {if(admin) await authorize(); await refresh(); if(admin||current.joined) connect();}
catch(error){showError(error); connection(false,'Bağlantı kurulamadı · Sayfayı yenileyin');}
