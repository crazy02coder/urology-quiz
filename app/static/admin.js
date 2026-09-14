import {$, api, authorize, showError, escape as e, letter, date} from './common.js';
let previewId, previewQuestions = [], saving = false;
const sessionRequests = new Map();
const deleteDialog = $('#delete-exam-dialog');
let deletingExam = null;
function requestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}
async function refresh() {
  const [exams, status] = await Promise.all([api('/api/admin/exams'),api('/api/admin/imports/status')]);
  $('#exam-count').textContent = exams.length;
  $('#exams').innerHTML = exams.length ? exams.map(exam => `<article class="card exam-row"><div class="exam-icon" aria-hidden="true">≡</div><div class="grow"><h3>${e(exam.title)}</h3><p class="muted">${exam.question_count} soru <span aria-hidden="true">·</span> ${date(exam.created_at)}</p></div><div class="exam-actions"><button class="secondary create-session" data-id="${e(exam.id)}">Sınavı başlat ↗</button><button class="delete-exam" data-id="${e(exam.id)}" data-title="${e(exam.title)}" aria-label="${e(exam.title)} sınavını sil">Sil</button></div></article>`).join('') : '<div class="empty"><span class="empty-icon" aria-hidden="true">≡</span><h3>Henüz kayıtlı sınav yok</h3><p>İlk sınavınızı soru dosyanızdan oluşturun.<br>Kaydetmeden önce tüm soruları kontrol edebilirsiniz.</p></div>';
  if (status.enabled) {
    $('#file').disabled = false; $('#file').accept = status.extensions.join(','); $('#preview-button').disabled = false;
    $('#import-note').textContent = `DOCX · Sınav adı ve dosya seçildikten sonra sorular otomatik hazırlanıp kaydedilir.`;
  }
}
$('#exams').addEventListener('click', async event => {
  const deleteButton = event.target.closest('.delete-exam');
  if (deleteButton) {
    deletingExam = {id: deleteButton.dataset.id, title: deleteButton.dataset.title};
    $('#delete-exam-description').textContent = `“${deletingExam.title}” adlı sınavı silmek istediğinize emin misiniz?`;
    $('#delete-exam-error').textContent = '';
    deleteDialog.showModal();
    return;
  }
  const button = event.target.closest('.create-session'); if (!button) return;
  button.disabled = true; showError(null);
  const id = button.dataset.id;
  if (!sessionRequests.has(id)) sessionRequests.set(id, requestId());
  try { const result = await api(`/api/admin/exams/${id}/sessions`, {request_id:sessionRequests.get(id)}); location.href = `/admin/sessions/${result.session_id}`; }
  catch(error) { showError(error); button.disabled = false; }
});
$('#confirm-delete-exam').onclick = async event => {
  if (!deletingExam) return;
  const button = event.currentTarget;
  button.disabled = true;
  $('#delete-exam-error').textContent = '';
  try {
    await api(`/api/admin/exams/${deletingExam.id}`, undefined, {method:'DELETE'});
    deleteDialog.close();
    await refresh();
  } catch(error) {
    $('#delete-exam-error').textContent = error.message;
  } finally {
    button.disabled = false;
  }
};
deleteDialog.addEventListener('close', () => {
  deletingExam = null;
  $('#delete-exam-error').textContent = '';
});
$('#logout').onclick = async () => { try { await api('/api/admin/logout', {}); location.href='/admin'; } catch(error) { showError(error); } };
$('#upload-form').onsubmit = async event => {
  event.preventDefault(); if (saving) return;
  saving = true;
  showError(null);
  const button = event.submitter || $('#preview-button');
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = 'Sınav hazırlanıyor…';
  $('#upload-status').hidden = true;
  $('#preview-section').hidden = true;
  previewId = null;
  previewQuestions = [];
  try {
    const file = $('#file').files[0];
    if (!file || file.size > 5*1024*1024) throw new Error('En fazla 5 MB büyüklüğünde bir soru dosyası seçin.');
    const preview = await api('/api/admin/imports/preview', file, {headers:{'X-Filename':encodeURIComponent(file.name),'X-Exam-Title':encodeURIComponent($('#title').value)}});
    await api('/api/admin/exams', {preview_id:preview.preview_id, review_confirmed:true});
    $('#upload-form').reset();
    $('#upload-status').textContent = `“${preview.title}” sınavı hazırlandı ve kaydedildi.`;
    $('#upload-status').hidden = false;
    await refresh();
  } catch(error) {
    showError(new Error(`Sınav hazırlanamadı: ${error.message}`));
  } finally {
    saving = false;
    button.disabled = false;
    button.textContent = originalText;
  }
};

// Eski manuel önizleme editörü geri dönüş gerekirse kullanılmak üzere pasif tutuluyor.
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
