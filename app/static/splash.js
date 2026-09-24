/* Tam ekran kurumsal açılış: EKG çizgisi ekranı boydan boya çizer, logo her
   R dalgasında nabız gibi atar. Dokunarak/tuşla geçilebilir; hareket azaltma
   tercihinde anında kapanır. CSP gereği satır içi stil yok, sadece sınıflar. */
const ECG = 'M0 100 H340 L362 86 L384 100 H420 L434 120 L460 18 L486 166 L504 100 H556 L586 72 L618 100 '
          + 'H740 L762 86 L784 100 H820 L834 120 L860 18 L886 166 L904 100 H956 L986 72 L1018 100 H1200';

export function playSplash() {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const root = document.createElement('div');
  root.className = 'splash';
  root.setAttribute('role', 'status');
  root.setAttribute('aria-label', 'Bilkent Şehir Hastanesi Personel Eğitim Platformu açılıyor');
  root.innerHTML = `<div class="splash-grid" aria-hidden="true"></div>
    <div class="splash-inner">
      <div class="splash-logo-wrap" aria-hidden="true"><span class="splash-halo"></span><span class="splash-halo splash-halo-late"></span>
        <img class="splash-logo" src="/static/img/saglik-bakanligi.png" alt=""></div>
      <svg class="splash-ecg" viewBox="0 0 1200 200" aria-hidden="true">
        <path class="ecg-base" d="${ECG}" pathLength="1"/>
        <path class="ecg-trace" d="${ECG}" pathLength="1"/>
        <path class="ecg-comet" d="${ECG}" pathLength="1"/>
      </svg>
      <h1 class="splash-title">Bilkent Şehir Hastanesi</h1>
      <p class="splash-sub">Personel Eğitim Platformu</p>
    </div>
    <span class="splash-skip" aria-hidden="true">Geçmek için dokunun</span>`;
  document.documentElement.classList.add('splash-open');
  document.body.appendChild(root);

  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    removeEventListener('keydown', finish);
    root.classList.add('splash-leave');
    document.documentElement.classList.remove('splash-open');
    setTimeout(() => root.remove(), 700);
  };
  root.addEventListener('click', finish);
  addEventListener('keydown', finish);
  setTimeout(finish, reduce ? 500 : 3100);
}
