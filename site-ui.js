(() => {
  'use strict';
  const script = document.currentScript;
  const base = new URL('./', script ? script.src : location.href);
  const url = path => new URL(path, base).href;
  const storageKey = 'acq.install.dismissed.v4';
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
  let signupAvailable = false;
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
          <p class="acq-site-footer__note">Știri selectate și rezumate automat din surse publice. Sursa originală este menționată în fiecare articol. Verifică informațiile importante în surse oficiale.</p>
        </div>
        <nav class="acq-site-footer__sections" aria-label="Secțiuni ACQ Media">
          <h2 class="acq-site-footer__heading">Secțiuni</h2>
          <ul><li><a href="${url('sport.html')}">Sport</a></li><li><a href="${url('hot.html')}">Hot</a></li><li><a href="${url('news.html')}">News</a></li><li><a href="${url('music.html')}">Music</a></li><li><a href="${url('arhiva.html')}">Arhivă</a></li></ul>
        </nav>
        <div class="acq-site-footer__studio">
          <h2 class="acq-site-footer__heading">Mai mult</h2>
          <ul><li><a href="${url('contact.html')}">Publicitate și contact</a></li><li><a href="mailto:media@acq.ro">media@acq.ro</a></li><li><a href="${url('newsletter/')}" data-acq-newsletter hidden>Newsletter</a></li></ul>
          <button class="acq-site-footer__install" type="button" data-acq-install>Adaugă pe ecran ↗</button>
        </div>
      </div>
      <div class="acq-site-footer__bottom"><span>© ${new Date().getFullYear()} ACQ Media</span><span>Știrile zilei, pe scurt.</span></div>`;
    const ending = document.querySelector('#ssub');
    if (ending) {
      footer.classList.add('acq-site-footer--compact');
      const title = ending.querySelector('.sub-title');
      if (title) title.textContent = 'Ai ajuns la final.';
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
    if (!ready || !invitationReady || (!isHome && !document.body.classList.contains('acq-section')) || isStandalone() || read(installedKey) === 'yes' || dismissedRecently() || !invitationAvailable() || document.querySelector('dialog[open]') || document.hidden) return;
    if (!toast) {
      toast = document.createElement('aside');
      toast.className = 'acq-install-card';
      toast.setAttribute('aria-label', 'Adaugă ACQ Media pe ecranul principal');
      toast.innerHTML = `<button class="acq-install-card__close" type="button" aria-label="Închide invitația">×</button><div class="acq-install-card__top"><img class="acq-install-card__icon" src="${url('icons/acq-media-192.png')}" alt="" width="42" height="42"><p class="acq-install-card__title">Știrile, la o atingere.</p></div><p class="acq-install-card__text">Adaugă ACQ Media pe ecranul principal al telefonului și deschide ediția dintr-o atingere.</p><div class="acq-install-card__actions"><button class="acq-install-card__action" type="button">${installPrompt ? 'Adaugă pe ecran' : 'Cum o adaugi'}</button><button class="acq-install-card__later" type="button">Mai târziu</button></div><a class="acq-install-card__newsletter" href="${url('newsletter/')}" data-acq-newsletter hidden>Primește ediția pe e-mail ↗</a>`;
      toast.querySelector('.acq-install-card__close').addEventListener('click', () => hideInvitation(true));
      toast.querySelector('.acq-install-card__later').addEventListener('click', () => hideInvitation(true));
      toast.querySelector('.acq-install-card__action').addEventListener('click', requestInstall);
      document.body.appendChild(toast);
    }
    toast.querySelector('.acq-install-card__action').textContent = installPrompt ? 'Adaugă pe ecran' : 'Cum o adaugi';
    toast.querySelector('[data-acq-newsletter]').hidden = !signupAvailable;
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

  function initReading() {
    const articleDialog = document.querySelector('.acq-section #modal-ov');
    if (!articleDialog || typeof ART === 'undefined') return;
    const slides = [...document.querySelectorAll('#track > .slide'), document.querySelector('#ssub')].filter(Boolean);
    const readingIndex = () => {
      const value = new URL(location.href).searchParams.get('articol');
      return value !== null && /^\d+$/.test(value) && ART[Number(value)] ? Number(value) : null;
    };
    const withArticle = index => {
      const next = new URL(location.href);
      if (index === null) next.searchParams.delete('articol');
      else next.searchParams.set('articol', String(index));
      return next;
    };
    let trigger = null, closing = false;
    function renderArticle(index, scrollToArticle) {
      if (index === null) {
        if (articleDialog.open) articleDialog.close();
        trigger?.focus({ preventScroll: true });
        return;
      }
      const article = ART[index];
      if (scrollToArticle) slides.find(slide => slide.dataset.articleIndex === String(index))?.scrollIntoView({ block: 'start' });
      for (const [id, value] of [['m-tag', article.tag], ['m-src', article.src || article.meta || ''], ['m-hed', article.hed]]) {
        articleDialog.querySelector('#' + id).textContent = value;
      }
      // The edition renderer escapes all text before wrapping it in paragraphs.
      articleDialog.querySelector('#m-txt').innerHTML = article.body;
      if (!articleDialog.open) articleDialog.showModal();
      articleDialog.scrollTop = 0;
    }
    function closeArticle() {
      if (closing || !articleDialog.open) return;
      if (history.state?.acqArticle === true) {
        closing = true;
        history.back();
      } else {
        history.replaceState(history.state, '', withArticle(null));
        renderArticle(null);
      }
    }
    window.openModal = index => {
      if (!ART[index]) return;
      trigger = document.activeElement;
      history.pushState({ ...history.state, acqArticle: true }, '', withArticle(index));
      renderArticle(index);
    };
    window.addEventListener('popstate', () => {
      closing = false;
      renderArticle(readingIndex(), false);
    });
    articleDialog.addEventListener('cancel', event => { event.preventDefault(); closeArticle(); });
    articleDialog.querySelector('.m-close').addEventListener('click', closeArticle);
    articleDialog.addEventListener('click', event => {
      if (event.target !== articleDialog) return;
      const r = articleDialog.getBoundingClientRect();
      if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) closeArticle();
    });
    slides.forEach((slide, index) => {
      slide.id ||= 'stire-' + (index + 1);
      slide.querySelector('button[data-next]')?.addEventListener('click', () => {
        const next = slides[index + 1];
        if (!next) return;
        next.scrollIntoView({ block: 'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
        const heading = next.querySelector('h2');
        if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
      });
    });
    const initial = readingIndex();
    if (initial !== null) renderArticle(initial, true);
  }

  function init() {
    addFooter();
    initReading();
    if (location.hostname === 'media.acq.ro' || location.hostname === 'www.media.acq.ro') {
      fetch(url('newsletter/?status=1'), {cache: 'no-store'}).then(r => r.ok ? r.json() : null).then(status => {
        signupAvailable = status?.signup === true;
        document.querySelectorAll('[data-acq-newsletter]').forEach(link => { link.hidden = !signupAvailable; });
      }).catch(() => {});
    }
    ready = true;
    window.setTimeout(() => { invitationReady = true; maybeOfferInstallation(); }, 3500);
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
