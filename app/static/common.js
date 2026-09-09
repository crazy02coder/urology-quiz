export const $ = (selector) => document.querySelector(selector);
export const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const letter = i => String.fromCharCode(65 + i);
export let csrf = '';
export async function api(path, data, extras = {}) {
  const headers = {'X-Requested-With':'BilkentQuiz', ...extras.headers};
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const options = {credentials:'same-origin', headers};
  if (data !== undefined) {
    options.method = 'POST';
    if (data instanceof File) { options.body = data; headers['Content-Type'] = 'application/octet-stream'; }
    else { options.body = JSON.stringify(data); headers['Content-Type'] = 'application/json'; }
  }
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error('Bağlantı kurulamadı. İnternet bağlantını kontrol edip yeniden dene.'); }
  const result = await response.json();
  if (!response.ok) {
    let detail = result.detail;
    if (Array.isArray(detail)) detail = detail.map(x => typeof x === 'string' ? x : 'Lütfen alanları kontrol edin.').join('\n');
    const error = new Error(detail || 'İşlem tamamlanamadı.'); error.status = response.status; throw error;
  }
  return result;
}
export async function authorize() {
  try { const me = await api('/api/admin/me'); csrf = me.csrf; }
  catch (error) { if (error.status === 401) location.href = '/admin'; throw error; }
}
export function showError(error) { $('#error').textContent = error?.message || ''; }
export const date = timestamp => new Date(timestamp * 1000).toLocaleString('tr-TR', {dateStyle:'medium',timeStyle:'short'});
