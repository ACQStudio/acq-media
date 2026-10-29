(() => {
  'use strict';
  const script = document.currentScript;
  const base = new URL('./', script ? script.src : location.href);
  const url = path => new URL(path, base).href;
  const storageKey = 'acq.install.dismissed.v3';
  const installedKey = 'acq.install.accepted';
  const httpsFailureKey = 'acq.https.probe.failedAt';
  const week = 7 * 24 * 60 * 60 * 1000;
  const read = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };
  const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isSafari = /Safari/.test(navigator.userAgent) && !/Chrome|Chromium|CriOS|Edg|FxiOS|OPiOS/.test(navigator.userAgent);
  const isAndroid = /Android/.test(navigator.userAgent);
  const isHome = location.pathname === base.pathname || location.pathname === new URL('index.html', base).pathname;
  let installPrompt = null;
  let toast = null;
  let dialog = null;
  let ready = false;
  let invitationReady = false;
  let previousFocus = null;

  async function upgradeToHttps() {
    const hostname = location.hostname.toLowerCase();
    if (location.protocol !== 'http:' || hostname === 'localhost' || hostname.endsWith('.localhost') || hostname === '127.0.0.1' || hostname === '[::1]' || hostname === '::1' || typeof fetch !== 'function' || typeof AbortController !== 'function') return;
    const failedAt = Number(read(httpsFailureKey));
    const age = Date.now() - failedAt;
    if (failedAt > 0 && age >= 0 && age < 5 * 60 * 1000) return;
    const probe = new URL('manifest.webmanifest', base);
    probe.protocol = 'https:';
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 2000);
    try {
      // The browser validates TLS normally. Do not follow redirects to another origin or back to HTTP.
      await fetch(probe.href, { mode: 'no-cors', credentials: 'omit', cache: 'no-store', redirect: 'error', signal: controller.signal });
      write(httpsFailureKey, '0');
      const securePage = new URL(location.href);
      securePage.protocol = 'https:';
      location.replace(securePage.href);
    } catch (_) {
      write(httpsFailureKey, String(Date.now()));
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function dismissedRecently() {
    const time = Number(read(storageKey));
    return Number.isFinite(time) && time > 0 && Date.now() - time < week;
  }

  function hideInvitation(remember) {
    if (remember) write(storageKey, String(Date.now()));
    if (toast) toast.hidden = true;
  }

  function addFooter() {
    if (document.querySelector('.acq-site-footer')) return;
    const footer = document.createElement('footer');
    footer.className = 'acq-site-footer';
    footer.setAttribute('aria-label', 'Despre ACQ Media și navigare');
    footer.innerHTML = `
      <div class="acq-site-footer__grid">
        <div class="acq-site-footer__identity">
          <a class="acq-site-footer__brand" href="${url('index.html')}">ACQ Media</a>
          <p class="acq-site-footer__powered">Realizat de <a href="https://acq.ro/" target="_blank" rel="noopener">ACQ Studio</a></p>
          <p class="acq-site-footer__note">ACQ Media selectează și rezumă automat informații din surse publice. Fiecare material include sursa originală. Pentru informațiile care îți influențează deciziile, consultă și sursele oficiale.</p>
        </div>
        <nav class="acq-site-footer__sections" aria-label="Secțiuni ACQ Media">
          <h2 class="acq-site-footer__heading">Secțiuni</h2>
          <ul><li><a href="${url('sport.html')}">Sport</a></li><li><a href="${url('hot.html')}">Hot · CanCan</a></li><li><a href="${url('news.html')}">Știri</a></li><li><a href="${url('music.html')}">Muzică</a></li><li><a href="${url('arhiva.html')}">Arhivă</a></li></ul>
        </nav>
        <div class="acq-site-footer__studio">
          <h2 class="acq-site-footer__heading">ACQ</h2>
          <ul><li><a href="https://acq.ro/" target="_blank" rel="noopener">Despre ACQ Studio ↗</a></li><li>Știri pe scurt. Sursa la vedere.</li></ul>
          <button class="acq-site-footer__install" type="button" data-acq-install>Adaugă pe ecran ↗</button>
        </div>
      </div>
      <div class="acq-site-footer__bottom">© ${new Date().getFullYear()} ACQ Media</div>`;
    const ending = document.querySelector('#ssub');
    if (ending) {
      footer.classList.add('acq-site-footer--compact');
      ending.classList.add('acq-has-footer');
      ending.appendChild(footer);
    } else {
      const wrapper = document.querySelector('body > .wrap');
      if (wrapper) wrapper.appendChild(footer);
      else { footer.classList.add('acq-site-footer--reading'); document.body.appendChild(footer); }
    }
    footer.querySelectorAll('[data-acq-install]').forEach(button => {
      button.hidden = isStandalone();
      button.addEventListener('click', requestInstall);
    });
  }

  function invitationAvailable() {
    return window.isSecureContext;
  }

  function maybeOfferInstallation() {
    if (!ready || !invitationReady || !isHome || isStandalone() || read(installedKey) === 'yes' || dismissedRecently() || !invitationAvailable() || document.querySelector('dialog[open]')) return;
    if (!toast) {
      toast = document.createElement('aside');
      toast.className = 'acq-install-card';
      toast.setAttribute('aria-label', 'Adaugă ACQ Media pe ecranul principal');
      toast.innerHTML = `<button class="acq-install-card__close" type="button" aria-label="Închide invitația">×</button><div class="acq-install-card__top"><img class="acq-install-card__icon" src="${url('icons/acq-192.png')}" alt="" width="42" height="42"><p class="acq-install-card__title">Știrile, la o atingere.</p></div><p class="acq-install-card__text">Adaugă ACQ Media pe ecranul principal și deschide direct ediția zilei.</p><div class="acq-install-card__actions"><button class="acq-install-card__action" type="button">${installPrompt ? 'Adaugă pe ecran' : 'Cum o adaugi'}</button><button class="acq-install-card__later" type="button">Mai târziu</button></div>`;
      toast.querySelector('.acq-install-card__close').addEventListener('click', () => hideInvitation(true));
      toast.querySelector('.acq-install-card__later').addEventListener('click', () => hideInvitation(true));
      toast.querySelector('.acq-install-card__action').addEventListener('click', requestInstall);
      document.body.appendChild(toast);
    }
    toast.querySelector('.acq-install-card__action').textContent = installPrompt ? 'Adaugă pe ecran' : 'Cum o adaugi';
    toast.hidden = false;
  }

  function closeDialog() {
    if (!dialog) return;
    if (typeof dialog.close === 'function' && dialog.open) dialog.close();
    else { dialog.removeAttribute('open'); dialog.hidden = true; }
    if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
  }

  function showInstructions() {
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.className = 'acq-install-dialog';
      dialog.setAttribute('aria-labelledby', 'acq-install-title');
      dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) closeDialog(); } });
      dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(); });
      dialog.addEventListener('keydown', event => {
        if (event.key === 'Escape') { event.preventDefault(); closeDialog(); }
        if (event.key !== 'Tab' || typeof dialog.showModal === 'function') return;
        const focusable = [...dialog.querySelectorAll('button,a[href]')];
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      });
      document.body.appendChild(dialog);
    }
    let content = '';
    if (!window.isSecureContext) {
      const secure = new URL(location.href); secure.protocol = 'https:';
      content = `<p>Pentru instalare, deschide versiunea securizată a site-ului.</p><p><a href="${secure.href}">Deschide ACQ Media prin HTTPS ↗</a></p>`;
    } else if (isIOS) {
      content = isSafari
        ? '<ol><li>Apasă butonul <strong>Partajează</strong> din Safari. În unele aranjamente îl găsești în meniul paginii.</li><li>Alege <strong>Adaugă pe ecranul principal</strong>.</li><li>Activează <strong>Deschide ca aplicație web</strong>, dacă apare, apoi apasă <strong>Adaugă</strong>.</li></ol>'
        : `<p>Deschide această pagină în Safari, apoi alege Partajează → Adaugă pe ecranul principal.</p><p><a href="${url('index.html')}">Pagina ACQ Media</a></p>`;
    } else if (isAndroid) {
      content = '<ol><li>Deschide meniul browserului <strong>⋮</strong>.</li><li>Alege <strong>Instalează aplicația</strong> sau <strong>Adaugă pe ecranul principal</strong>.</li><li>Confirmă adăugarea. Dacă opțiunea lipsește, încearcă pagina în Chrome.</li></ol>';
    } else if (isSafari && /Mac/.test(navigator.platform)) {
      content = '<p>Pe Mac, deschide site-ul în Safari.</p><ol><li>Deschide meniul <strong>Fișier</strong>.</li><li>Alege <strong>Adaugă în Dock</strong>.</li><li>Confirmă numele <strong>ACQ Media</strong> și apasă <strong>Adaugă</strong>.</li></ol>';
    } else if (/Chrome|Chromium|Edg/.test(navigator.userAgent)) {
      content = '<p>Caută pictograma de instalare din bara de adrese sau opțiunea de instalare din meniul browserului. Dacă nu apare, browserul nu oferă instalarea acestei pagini în acest moment.</p>';
    } else {
      content = '<p>Poți salva ACQ Media ca semn de carte. Pentru o aplicație separată, deschide site-ul în Chrome, Edge sau Safari pe Mac.</p>';
    }
    dialog.innerHTML = `<h2 id="acq-install-title">ACQ Media pe ecranul tău.</h2>${content}<button type="button" class="acq-install-dialog__done">Am înțeles</button>`;
    dialog.querySelector('button').addEventListener('click', closeDialog);
    previousFocus = document.activeElement;
    dialog.hidden = false;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else { dialog.classList.add('acq-dialog-fallback'); dialog.setAttribute('open', ''); dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true'); }
    dialog.querySelector('button').focus();
  }

  async function requestInstall() {
    if (isStandalone()) return;
    hideInvitation(true);
    if (!installPrompt) { showInstructions(); return; }
    const prompt = installPrompt;
    installPrompt = null;
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome === 'accepted') write(installedKey, 'yes');
    } catch (_) { showInstructions(); }
  }

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    maybeOfferInstallation();
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    write(installedKey, 'yes');
    hideInvitation(false);
    document.querySelectorAll('[data-acq-install]').forEach(button => { button.hidden = true; });
  });

  function init() {
    addFooter();
    ready = true;
    window.setTimeout(() => { invitationReady = true; maybeOfferInstallation(); }, 4500);
    if ('serviceWorker' in navigator && window.isSecureContext) {
      const register = () => navigator.serviceWorker.register(url('sw.js'), { scope: base.pathname }).catch(() => {});
      if (document.readyState === 'complete') register();
      else window.addEventListener('load', register, { once: true });
    }
  }
  upgradeToHttps();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
