import {$, api, showError} from './common.js';
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true; showError(null);
  try { await api('/api/login', {password:$('#password').value}); location.href = '/admin'; }
  catch(error) { showError(error); }
  finally { button.disabled = false; }
});
