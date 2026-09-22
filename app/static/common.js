export const $ = (selector) => document.querySelector(selector);
export const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const letter = i => String.fromCharCode(65 + i);
export let csrf = '';
export async function api(path, data, extras = {}) {
  const headers = {'X-Requested-With':'BilkentQuiz', ...extras.headers};
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const options = {credentials:'same-origin', headers};
  if (extras.method) options.method = extras.method;
  if (data !== undefined) {
    options.method ||= 'POST';
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

/* --- Bildirimler (toast) ---------------------------------------------------
   Harici kütüphane yok: CSP yalnızca 'self' script'e izin veriyor.
   Aynı metin üst üste gelirse yinelenmez, sayaç artar. */
const TOAST_ICONS = {success:'✓', error:'!', warn:'⚠', info:'i'};
let toastStack;
export function toast(message, kind = 'info', timeout = 4600) {
  const text = String(message ?? '').trim();
  if (!text) return;
  if (!toastStack) {
    toastStack = document.createElement('div');
    toastStack.className = 'toast-stack';
    toastStack.setAttribute('role', 'region');
    toastStack.setAttribute('aria-label', 'Bildirimler');
    document.body.appendChild(toastStack);
  }
  const last = toastStack.lastElementChild;
  if (last && last.dataset.text === text) {
    const counter = last.querySelector('.toast-repeat');
    const times = Number(last.dataset.times || 1) + 1;
    last.dataset.times = times;
    counter.textContent = `×${times}`;
    counter.hidden = false;
    return;
  }
  const item = document.createElement('div');
  item.className = `toast toast-${kind}`;
  item.dataset.text = text;
  item.setAttribute('role', kind === 'error' ? 'alert' : 'status');
  const icon = document.createElement('span');
  icon.className = 'toast-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = TOAST_ICONS[kind] || TOAST_ICONS.info;
  const body = document.createElement('p');
  body.className = 'toast-text';
  body.textContent = text;
  const repeat = document.createElement('span');
  repeat.className = 'toast-repeat';
  repeat.hidden = true;
  const close = document.createElement('button');
  close.className = 'toast-close';
  close.type = 'button';
  close.setAttribute('aria-label', 'Bildirimi kapat');
  close.textContent = '×';
  item.append(icon, body, repeat, close);
  toastStack.appendChild(item);
  const remove = () => {
    if (!item.isConnected) return;
    item.classList.add('toast-leaving');
    item.addEventListener('animationend', () => item.remove(), {once:true});
    setTimeout(() => item.remove(), 400);
  };
  close.onclick = remove;
  if (timeout) setTimeout(remove, timeout + Number(item.dataset.times || 1) * 250);
}

export const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/* Listelere kademeli giriş gecikmesi verir. CSP style-src 'self' olduğu için
   satır içi style niteliği değil, CSSOM üzerinden özel değişken yazılır. */
export function stagger(elements, step = 45, max = 12) {
  [...elements].forEach((element, i) => element.style.setProperty('--stagger', `${Math.min(i, max) * step}ms`));
}

/* Sayıyı 0'dan hedefe sayar; hareket azaltma tercihinde anında yazar. */
export function countUp(element, target, {duration = 900, suffix = ''} = {}) {
  const value = Number(target) || 0;
  const decimals = Number.isInteger(value) ? 0 : 1;
  if (reduceMotion() || !duration) { element.textContent = value.toFixed(decimals) + suffix; return; }
  const start = performance.now();
  const step = now => {
    const progress = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = (value * eased).toFixed(decimals) + suffix;
    if (progress < 1) requestAnimationFrame(step);
    else element.textContent = value.toFixed(decimals) + suffix;
  };
  requestAnimationFrame(step);
}

/* Yüzde çubuklarını render sonrası genişletir (CSS geçişi tetiklenir). */
export function growBars(root = document) {
  const bars = root.querySelectorAll('[data-percent]');
  bars.forEach(bar => bar.style.setProperty('--fill', '0%'));
  requestAnimationFrame(() => requestAnimationFrame(() => {
    bars.forEach(bar => bar.style.setProperty('--fill', `${Math.max(0, Math.min(100, Number(bar.dataset.percent) || 0))}%`));
  }));
}

export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/* --- Panoya kopyalama ------------------------------------------------------
   navigator.clipboard yalnızca güvenli bağlamda (HTTPS veya localhost) vardır.
   Hastane ağında uygulama http://IP:8000 ile açıldığında tanımsızdır; bu yüzden
   seçim + execCommand yedeği tutuluyor. */
export async function copyText(text, input) {
  try {
    if (navigator.clipboard && isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* yedeğe düşülür */ }
  if (!input) return false;
  const readonly = input.hasAttribute('readonly');
  try {
    input.removeAttribute('readonly');   // iOS Safari salt okunur alanı seçtirmez
    input.focus({preventScroll:true});
    input.select();
    input.setSelectionRange(0, String(text).length);
    return document.execCommand('copy');
  } catch { return false; }
  finally { if (readonly) input.setAttribute('readonly', ''); }
}

/* --- Tema ------------------------------------------------------------------
   Seçim yapılmadıysa işletim sistemi tercihi geçerlidir (CSS media query ile),
   böylece modül yüklenene kadar yanlış temada yanıp sönme olmaz. */
const THEME_KEY = 'bilkent-theme';
export function storedTheme() {
  try { const value = localStorage.getItem(THEME_KEY); return value === 'dark' || value === 'light' ? value : null; }
  catch { return null; }
}
export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme) root.dataset.theme = theme; else delete root.dataset.theme;
  try { theme ? localStorage.setItem(THEME_KEY, theme) : localStorage.removeItem(THEME_KEY); } catch { /* yok sayılır */ }
  document.querySelectorAll('[data-theme-toggle]').forEach(syncThemeButton);
}
export const activeTheme = () =>
  storedTheme() || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
function syncThemeButton(button) {
  const dark = activeTheme() === 'dark';
  button.setAttribute('aria-pressed', String(dark));
  button.setAttribute('aria-label', dark ? 'Açık temaya geç' : 'Koyu temaya geç');
  button.title = button.getAttribute('aria-label');
  const icon = button.querySelector('.theme-icon');
  const text = button.querySelector('.theme-text');
  if (icon) icon.textContent = dark ? '☀' : '☾';
  if (text) text.textContent = dark ? 'Açık tema' : 'Koyu tema';
}
export function initTheme() {
  const stored = storedTheme();
  if (stored) document.documentElement.dataset.theme = stored;
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
    syncThemeButton(button);
    button.addEventListener('click', () => applyTheme(activeTheme() === 'dark' ? 'light' : 'dark'));
  });
  // Seçim yapılmamışsa sistem tercihi değiştiğinde buton etiketi güncel kalsın.
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (!storedTheme()) document.querySelectorAll('[data-theme-toggle]').forEach(syncThemeButton);
  });
}

/* --- Akordiyon -------------------------------------------------------------
   <details> kapalıyken içerik display:none olduğu için geçiş çalışmaz;
   bu yüzden buton + grid satır geçişi kullanılıyor. */
export function initAccordion(root) {
  root.addEventListener('click', event => {
    const head = event.target.closest('[data-acc]');
    if (!head || !root.contains(head)) return;
    const item = head.closest('.acc');
    const open = item.classList.toggle('is-open');
    head.setAttribute('aria-expanded', String(open));
  });
}
