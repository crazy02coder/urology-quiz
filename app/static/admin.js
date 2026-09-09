import {$, api, authorize, showError, escape as e, letter, date} from './common.js';
let previewId;
const sessionRequests = new Map();
const phaseNames = {lobby:'Katılımcılar bekleniyor',question:'Soru açık',results:'Sonuçlar',finished:'Tamamlandı'};
async function refresh() {
  const [exams, sessions, status] = await Promise.all([api('/api/admin/exams'),api('/api/admin/sessions'),api('/api/admin/imports/status')]);
  $('#exam-count').textContent = exams.length;
  $('#exams').innerHTML = exams.length ? exams.map(exam => `<article class="card exam-row"><div class="exam-icon" aria-hidden="true">≡</div><div class="grow"><h3>${e(exam.title)}</h3><p class="muted">${exam.question_count} soru <span aria-hidden="true">·</span> ${date(exam.created_at)}</p></div><button class="secondary create-session" data-id="${e(exam.id)}">Canlı oturum oluştur ↗</button></article>`).join('') : '<div class="empty"><span class="empty-icon" aria-hidden="true">≡</span><h3>Henüz kayıtlı sınav yok</h3><p>İlk sınavınızı soru dosyanızdan oluşturun.<br>Kaydetmeden önce tüm soruları kontrol edebilirsiniz.</p></div>';
  $('#sessions').innerHTML = sessions.length ? sessions.map(s => `<a href="/admin/sessions/${e(s.id)}" class="card session-row"><div><h3>${e(s.title)}</h3><span class="muted">${date(s.created_at)} · ${s.participant_count} katılımcı</span></div><span class="badge ${s.phase==='finished'?'neutral':''}">${phaseNames[s.phase]}</span><span aria-hidden="true">→</span></a>`).join('') : '<div class="empty small-empty">Bir sınavdan canlı oturum oluşturduğunuzda burada görünecek.</div>';
  if (status.enabled) {
    $('#file').disabled = false; $('#file').accept = status.extensions.join(','); $('#preview-button').disabled = false;
    $('#import-note').textContent = `DOCX · Örnek soru dosyanızdaki düzeni kullanın. İpuçları ve açıklamalar süre bittikten sonra gösterilir.`;
  }
}
$('#exams').addEventListener('click', async event => {
  const button = event.target.closest('.create-session'); if (!button) return;
  button.disabled = true; showError(null);
  const id = button.dataset.id;
  if (!sessionRequests.has(id)) sessionRequests.set(id, crypto.randomUUID());
  try { const result = await api(`/api/admin/exams/${id}/sessions`, {request_id:sessionRequests.get(id)}); location.href = `/admin/sessions/${result.session_id}`; }
  catch(error) { showError(error); button.disabled = false; }
});
$('#logout').onclick = async () => { try { await api('/api/admin/logout', {}); location.href='/admin'; } catch(error) { showError(error); } };
$('#upload-form').onsubmit = async event => {
  event.preventDefault(); showError(null); const button = event.submitter; button.disabled = true;
  try {
    const file = $('#file').files[0];
    if (!file || file.size > 5*1024*1024) throw new Error('En fazla 5 MB büyüklüğünde bir soru dosyası seçin.');
    const preview = await api('/api/admin/imports/preview', file, {headers:{'X-Filename':encodeURIComponent(file.name),'X-Exam-Title':encodeURIComponent($('#title').value)}});
    previewId = preview.preview_id;
    $('#preview').innerHTML = `<h3>${e(preview.title)}</h3>` + preview.questions.map((q,i) => `<article class="preview-question"><span class="eyebrow">${e(q.topic)}</span><h3>${i+1}. ${e(q.text)}</h3><ol class="preview-options">${q.options.map((o,j) => `<li class="${q.correct===j?'correct-text':''}">${letter(j)}. ${e(o)} ${q.correct===j?' ✓ Doğru cevap':''}</li>`).join('')}</ol>${q.hint?`<p class="muted">İpucu: ${e(q.hint)}</p>`:""}${q.explanation?`<p>${e(q.explanation)}</p>`:""}</article>`).join('');
    $('#preview-section').hidden = false; $('#preview-section').scrollIntoView({behavior:'auto'});
  } catch(error) { showError(error); } finally { button.disabled = false; }
};
$('#close-preview').onclick = () => { $('#preview-section').hidden = true; previewId = null; };
$('#save-exam').onclick = async event => {
  event.target.disabled = true; showError(null);
  try { await api('/api/admin/exams', {preview_id:previewId}); $('#preview-section').hidden=true; $('#upload-form').reset(); await refresh(); }
  catch(error) { showError(error); } finally { event.target.disabled=false; }
};
try { await authorize(); await refresh(); } catch(error) { showError(error); }
