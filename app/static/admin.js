import {$, api, authorize, showError, escape as e, letter, date} from './common.js';
let previewId, previewQuestions = [], saving = false;
const sessionRequests = new Map();
const phaseNames = {lobby:'Katılımcılar bekleniyor',question:'Soru açık',results:'Sonuçlar',finished:'Tamamlandı'};
async function refresh() {
  const [exams, sessions, status] = await Promise.all([api('/api/admin/exams'),api('/api/admin/sessions'),api('/api/admin/imports/status')]);
  $('#exam-count').textContent = exams.length;
  $('#exams').innerHTML = exams.length ? exams.map(exam => `<article class="card exam-row"><div class="exam-icon" aria-hidden="true">≡</div><div class="grow"><h3>${e(exam.title)}</h3><p class="muted">${exam.question_count} soru <span aria-hidden="true">·</span> ${date(exam.created_at)}</p></div><button class="secondary create-session" data-id="${e(exam.id)}">Canlı oturum oluştur ↗</button></article>`).join('') : '<div class="empty"><span class="empty-icon" aria-hidden="true">≡</span><h3>Henüz kayıtlı sınav yok</h3><p>İlk sınavınızı soru dosyanızdan oluşturun.<br>Kaydetmeden önce tüm soruları kontrol edebilirsiniz.</p></div>';
  $('#sessions').innerHTML = sessions.length ? sessions.map(s => `<a href="/admin/sessions/${e(s.id)}" class="card session-row"><div><h3>${e(s.title)}</h3><span class="muted">${date(s.created_at)} · ${s.participant_count} katılımcı</span></div><span class="badge ${s.phase==='finished'?'neutral':''}">${phaseNames[s.phase]}</span><span aria-hidden="true">→</span></a>`).join('') : '<div class="empty small-empty">Bir sınavdan canlı oturum oluşturduğunuzda burada görünecek.</div>';
  if (status.enabled) {
    $('#file').disabled = false; $('#file').accept = status.extensions.join(','); $('#preview-button').disabled = false;
    $('#import-note').textContent = `DOCX · Farklı soru ve şık düzenleri okunur; önizlemede kontrol edip düzenleyin. İpuçları ve açıklamalar süre bittikten sonra gösterilir.`;
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
  event.preventDefault(); if (saving) return;
  showError(null); const button = event.submitter; button.disabled = true;
  $('#preview-section').hidden = true; previewId = null; previewQuestions = []; invalidateReview();
  try {
    const file = $('#file').files[0];
    if (!file || file.size > 5*1024*1024) throw new Error('En fazla 5 MB büyüklüğünde bir soru dosyası seçin.');
    const preview = await api('/api/admin/imports/preview', file, {headers:{'X-Filename':encodeURIComponent(file.name),'X-Exam-Title':encodeURIComponent($('#title').value)}});
    previewId = preview.preview_id;
    previewQuestions = preview.questions;
    $('#preview-info').innerHTML = `<h3>${e(preview.title)}</h3><p class="notice">Alanları düzenleyebilir, soru ve şık ekleyip silebilirsiniz. Doğru cevapları kaynak dosyanızla karşılaştırın.</p>${warningList(preview.warnings)}<details><summary>Word’den okunan tüm metni göster</summary><pre class="source-text">${e(preview.source_text)}</pre></details>`;
    $('#preview-error').textContent = '';
    renderPreview();
    $('#preview-section').hidden = false; $('#preview-section').scrollIntoView({behavior:'auto'});
  } catch(error) { showError(error); } finally { button.disabled = false; }
};
function warningList(warnings = []) {
  return warnings.length ? `<div class="notice"><strong>Aktarım notları</strong><ul>${warnings.map(w => `<li>${e(w)}</li>`).join('')}</ul></div>` : '';
}
function invalidateReview() {
  $('#review-confirmed').checked = false;
  $('#save-exam').disabled = true;
}
function field(i, key, label, limit, rows = 2) {
  return `<label for="q-${i}-${key}">${label}</label><textarea id="q-${i}-${key}" data-field="${key}" maxlength="${limit}" rows="${rows}">${e(previewQuestions[i][key])}</textarea>`;
}
function renderPreview() {
  invalidateReview();
  $('#add-question').disabled = previewQuestions.length >= 300;
  $('#preview').innerHTML = previewQuestions.map((q, i) => `<article class="preview-question" data-question="${i}">
    <div class="section-heading"><h3>Soru ${i+1}</h3><button type="button" class="text-button" data-action="remove-question">Soruyu sil</button></div>
    ${warningList(q.warnings)}
    ${field(i, 'text', 'Soru metni', 3000, 3)}
    <div class="edit-options">${q.options.map((o,j) => `<div class="edit-option"><div class="grow"><label for="q-${i}-option-${j}">${letter(j)} şıkkı</label><textarea id="q-${i}-option-${j}" data-option="${j}" maxlength="1000" rows="2">${e(o)}</textarea></div><button type="button" class="text-button" data-action="remove-option" data-index="${j}" aria-label="${letter(j)} şıkkını sil" ${q.options.length<=2?'disabled':''}>Sil</button></div>`).join('')}</div>
    <button type="button" class="secondary" data-action="add-option" ${q.options.length>=5?'disabled':''}>+ Şık ekle</button>
    <label for="q-${i}-correct">Doğru cevap</label><select id="q-${i}-correct" data-field="correct"><option value="" ${q.correct===null?'selected':''}>Doğru cevabı seçin</option>${q.options.map((o,j) => `<option value="${j}" ${q.correct===j?'selected':''}>${letter(j)} şıkkı</option>`).join('')}</select>
    <details><summary>Konu, ipucu ve açıklama</summary>${field(i,'topic','Konu',5000,1)}${field(i,'hint','İpucu',5000)}${field(i,'explanation','Açıklama',5000,3)}</details>
    ${q.source_text?`<details><summary>Bu sorunun kaynak metni</summary><pre class="source-text">${e(q.source_text)}</pre></details>`:''}
  </article>`).join('');
}
$('#preview').addEventListener('input', event => {
  if (saving) return;
  const card = event.target.closest('[data-question]'); if (!card) return;
  const q = previewQuestions[Number(card.dataset.question)];
  const target = event.target;
  if (target.dataset.option !== undefined) q.options[Number(target.dataset.option)] = target.value;
  else if (target.dataset.field) q[target.dataset.field] = target.dataset.field === 'correct' ? (target.value === '' ? null : Number(target.value)) : target.value;
  invalidateReview();
});
$('#preview').addEventListener('click', event => {
  const button = event.target.closest('[data-action]'); if (!button || saving) return;
  const index = Number(button.closest('[data-question]').dataset.question);
  const q = previewQuestions[index];
  if (button.dataset.action === 'remove-question') previewQuestions.splice(index, 1);
  if (button.dataset.action === 'add-option' && q.options.length < 5) q.options.push('');
  if (button.dataset.action === 'remove-option' && q.options.length > 2) {
    const option = Number(button.dataset.index); q.options.splice(option, 1);
    if (q.correct === option) q.correct = null;
    else if (q.correct !== null && q.correct > option) q.correct--;
  }
  renderPreview();
});
$('#add-question').onclick = () => {
  if (saving || previewQuestions.length >= 300) return;
  previewQuestions.push({text:'',options:['',''],correct:null,topic:'',hint:'',explanation:''});
  renderPreview();
  $('#preview').lastElementChild.querySelector('textarea').focus();
};
$('#review-confirmed').onchange = event => { $('#save-exam').disabled = saving || !event.target.checked; };
$('#close-preview').onclick = () => {
  if (saving) return;
  $('#preview-section').hidden = true; previewId = null; previewQuestions = []; invalidateReview();
};
$('#save-exam').onclick = async event => {
  if (saving || !previewId || !$('#review-confirmed').checked) return;
  saving = true; event.target.disabled = true; $('#preview-editor').disabled = true;
  $('#close-preview').disabled = true; $('#preview-button').disabled = true;
  $('#preview-error').textContent = ''; showError(null);
  const questions = previewQuestions.map(({text,options,correct,topic,hint,explanation}) => ({text,options,correct,topic,hint,explanation}));
  try {
    await api('/api/admin/exams', {preview_id:previewId, questions, review_confirmed:true});
    $('#preview-section').hidden=true; previewId=null; previewQuestions=[]; $('#upload-form').reset();
    await refresh();
  } catch(error) {
    if (previewId) $('#preview-error').textContent = error.message;
    else showError(error);
  } finally {
    saving = false; $('#preview-editor').disabled = false; $('#close-preview').disabled = false;
    $('#preview-button').disabled = false;
    event.target.disabled = !previewId || !$('#review-confirmed').checked;
  }
};
try { await authorize(); await refresh(); } catch(error) { showError(error); }
