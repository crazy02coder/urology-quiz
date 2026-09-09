import {$, api, authorize, showError, escape as e, letter} from './common.js';
const admin = location.pathname.startsWith('/admin/');
const sid = location.pathname.split('/').filter(Boolean).at(-1);
const base = admin ? `/api/admin/sessions/${sid}` : `/api/sessions/${sid}`;
const stage = $('#stage');
let current, signature='', socket, online=false, retry=0, stopped=false, pending=false, anchor=0, remaining=0;
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
function apply(state) {
  current=state; remaining=state.remaining_seconds || 0; anchor=performance.now();
  const {server_now, remaining_seconds, ...stable} = state;
  const next=JSON.stringify(stable);
  if (signature!==next) {signature=next; render();}
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
      stopped=true; connection(false,'Oturum doğrulanamadı · Sayfayı yenileyin');
      showError(new Error(admin?'Yönetici oturumunuz sona erdi. Eğitimler bağlantısından yeniden giriş yapın.':'Katılım oturumu doğrulanamadı. Sayfayı yenile.')); return;
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
    stage.innerHTML=`<section class="card join-card"><span class="eyebrow">EĞİTİME KATIL</span><h1>${e(current.title)}</h1>${current.phase==='lobby'?'<p class="muted">Eğitim boyunca seni bu adla tanıyacağız.</p><form id="join-form"><label for="nickname">Takma adın</label><input id="nickname" placeholder="Örn. kizilbaris" minlength="2" maxlength="30" autocomplete="nickname" required><button class="primary full">Oturuma katıl →</button></form>':'<p>Bu oturum başladı veya tamamlandı. Yeni katılımcı alınmıyor.</p><p class="muted">Daha önce katıldıysan aynı tarayıcı ve cihazdan bağlantıyı aç.</p>'}</section>`;
    return;
  }
  if(current.phase==='lobby') {
    stage.innerHTML=title()+(admin?`<div class="lobby-grid"><section class="card qr-card"><span class="eyebrow">KATILMAK İÇİN QR KODU OKUTUN</span><img class="qr" src="${base}/qr.png" alt="Bu canlı oturuma katılım QR kodu"><div class="qr-actions"><a class="button secondary" href="${base}/qr.png" download="bilkent-katilim.png">PNG indir ↓</a><button id="copy" class="secondary">Bağlantıyı kopyala</button></div><label class="sr-only" for="join-url">Katılım bağlantısı</label><input id="join-url" class="link-input" value="${e(current.join_url)}" readonly></section><section class="card lobby-people"><div class="section-heading"><h2>Katılımcılar</h2><span class="count">${current.participant_count}</span></div><p class="muted">Herkes katıldığında eğitimi başlatın.</p><div class="names">${current.participants.map(name=>`<span class="name-chip">${e(name)}</span>`).join('')||'<p class="empty-people">İlk katılımcı bekleniyor…</p>'}</div><div class="lobby-bottom"><p class="footnote">Başlattıktan sonra yeni katılımcı alınmaz.<br>Her soru 45 saniye açık kalır.</p><button class="primary full" data-control="start">Başlat →</button></div></section></div>`:`<section class="card waiting centered"><span class="waiting-dot" aria-hidden="true"></span><span class="eyebrow">HAZIRSIN, ${e(current.nickname)}</span><h2>Yöneticinin başlatması<br>bekleniyor</h2><p class="muted">İlk soru başladığında burada görünecek.</p><span class="badge">Her soru için 45 saniye</span></section>`);
  } else if(current.phase==='question'||current.phase==='results') {
    const q=current.question, results=current.phase==='results';
    stage.innerHTML=title()+`<section class="question-panel"><div class="question-meta"><span class="eyebrow">SORU ${current.question_index+1} / ${current.question_count}</span>${results?'<span class="badge">Cevaplama sona erdi</span>':'<div class="timer" role="timer" aria-label="Kalan saniye"><strong id="timer">45</strong><span>saniye</span></div>'}</div>${q.topic?`<p class="topic">${e(q.topic)}</p>`:""}<h2 class="question-text">${e(q.text)}</h2><div class="options">${q.options.map((option,i)=>results?`<div class="option result-option ${q.correct===i?'correct':'incorrect'}"><span class="letter">${letter(i)}</span><div class="grow">${e(option)}<small>${q.correct===i?'✓ Doğru cevap':'✕'}${current.own_choice===i?' · Senin cevabın':''}</small></div><span class="result-count">${current.distribution[i]}<small>cevap</small></span></div>`:admin?`<div class="option"><span class="letter">${letter(i)}</span><span>${e(option)}</span></div>`:`<button class="option ${current.own_choice===i?'selected':''}" data-choice="${i}" ${current.own_choice!=null?'disabled':''}><span class="letter">${letter(i)}</span><span>${e(option)}</span>${current.own_choice===i?'<span class="selected-mark">✓</span>':''}</button>`).join('')}</div>${results?chart()+explanation():`<p class="answer-status" role="status">${!admin&&current.own_choice!=null?'✓ Cevabın kaydedildi, sonuçlar bekleniyor':admin?'Cevaplar alınıyor. Sonuçlar 45 saniyenin sonunda açılacak.':'Cevabını seç. Kaydettikten sonra değiştiremezsin.'}</p>`}</section>`;
    if(results) stage.insertAdjacentHTML('beforeend',`<div class="stage-bottom"><p class="muted">${admin?'Sonuçları değerlendirin; hazır olduğunuzda devam edin.':'Yöneticinin devam etmesi bekleniyor.'}</p>${admin?`<button class="primary" data-control="${current.question_index+1===current.question_count?'finish':'next'}">${current.question_index+1===current.question_count?'Oturumu bitir':'Sonraki soru →'}</button>`:''}</div>`);
  } else if(current.phase==='finished') {
    stage.innerHTML=title()+`<section class="card completed centered"><span class="completion-icon" aria-hidden="true">✓</span><span class="eyebrow">EĞİTİM TAMAMLANDI</span><h2>${admin?'Oturum tamamlandı':'Katıldığın için teşekkürler'}</h2>${admin?'<p class="muted">Katılımcıların soru bazında yanıtları aşağıda.</p><button id="history-button" class="secondary">Cevap kayıtlarını göster</button>':`<p class="muted">İşte bu eğitimdeki yanıtların.</p><div class="summary"><div><strong>${current.summary.correct}</strong><span>✓ Doğru</span></div><div><strong>${current.summary.wrong}</strong><span>✕ Yanlış</span></div><div><strong>${current.summary.blank}</strong><span>– Boş</span></div></div>`}</section><div id="history"></div>`;
  }
}
function explanation() {
  const q=current.question;
  return q.explanation||q.hint?`<section class="explanation"><h3>Açıklama</h3>${q.explanation?`<p>${e(q.explanation)}</p>`:''}${q.hint?`<p class="muted">İpucu: ${e(q.hint)}</p>`:''}</section>`:'';
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
stage.addEventListener('click',async event=>{
  const answerButton=event.target.closest('[data-choice]'), controlButton=event.target.closest('[data-control]');
  if(answerButton||controlButton) {
    if(pending||!online) return;
    pending=true; updateTimer(); showError(null);
    try {
      if(answerButton) await api(`${base}/answers`,{question_id:current.question.id,choice:Number(answerButton.dataset.choice)});
      else await api(`${base}/control`,{action:controlButton.dataset.control,expected_version:current.version});
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
  if(event.target.closest('#history-button')) {
    try {
      const data=await api(`${base}/history`);
      $('#history').innerHTML=`<section class="card history-card"><h2>Katılımcı yanıtları</h2><div class="table-scroll"><table><caption class="sr-only">Soru bazında verilen cevaplar</caption><thead><tr><th>Takma ad</th>${data.questions.map((q,i)=>`<th>${i+1}. soru</th>`).join('')}</tr></thead><tbody>${data.participants.map(p=>`<tr><th>${e(p.nickname)}</th>${data.questions.map(q=>{const answer=p.answers[q.id];return `<td>${answer==null?'– Boş':`${letter(answer)} · ${e(q.options[answer])} ${answer===q.correct?'✓ Doğru':'✕ Yanlış'}`}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div><div class="question-key">${data.questions.map((q,i)=>`<p><strong>${i+1}. ${e(q.text)}</strong><br>✓ Doğru cevap: ${letter(q.correct)} · ${e(q.options[q.correct])}</p>`).join('')}</div></section>`;
      $('#history-button').hidden=true;
    } catch(error){showError(error);}
  }
});
try {if(admin) await authorize(); await refresh(); if(admin||current.joined) connect();}
catch(error){showError(error); connection(false,'Bağlantı kurulamadı · Sayfayı yenileyin');}
