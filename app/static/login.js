import {$, api, showError, toast, initTheme} from './common.js';
import {playSplash} from './splash.js';
playSplash();
const password = $('#password');
const toggle = $('#toggle-password');
toggle.onclick = () => {
  const shown = password.type === 'text';
  password.type = shown ? 'password' : 'text';
  toggle.setAttribute('aria-pressed', String(!shown));
  toggle.setAttribute('aria-label', shown ? 'Şifreyi göster' : 'Şifreyi gizle');
  toggle.title = shown ? 'Şifreyi göster' : 'Şifreyi gizle';
  toggle.classList.toggle('is-shown', !shown);
  $('.password-toggle-text').textContent = shown ? 'Göster' : 'Gizle';
  // Odak ve imleç sonda kalsın; kullanıcı yazmaya devam edebilsin.
  const end = password.value.length;
  password.focus();
  password.setSelectionRange(end, end);
};
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; showError(null);
  try { await api('/api/login', {password:password.value}); location.href = '/admin'; }
  catch(error) { showError(error); toast(error.message, error.status === 429 ? 'warn' : 'error'); }
  finally { button.disabled = false; }
});
initTheme();
