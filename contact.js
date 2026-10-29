(() => {
  'use strict';
  const form = document.querySelector('#advertising-form');
  const sectionField = document.querySelector('#contact-section');
  const backLink = document.querySelector('#back-link');
  const status = document.querySelector('#contact-status');
  const sectionNames = { all: 'Toate secțiunile', sport: 'Sport', hot: 'Hot', news: 'News', music: 'Music' };
  const section = new URLSearchParams(location.search).get('sectiune');
  if (section && Object.hasOwn(sectionNames, section)) {
    sectionField.value = section;
    if (section !== 'all') backLink.href = `${section}.html`;
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const values = new FormData(form);
    const read = key => String(values.get(key) || '').trim();
    const selected = sectionNames[read('section')] || sectionNames.all;
    const company = read('company');
    const subject = `Publicitate ACQ Media · ${selected}`;
    const body = [
      'Bună,',
      '',
      'Aș vrea să discutăm despre o campanie în ACQ Media.',
      '',
      `Nume: ${read('name')}`,
      `E-mail de contact: ${read('email')}`,
      ...(company ? [`Companie: ${company}`] : []),
      `Secțiune: ${selected}`,
      '',
      'Despre campanie:',
      read('brief'),
    ].join('\n');
    status.textContent = 'Confirmă trimiterea în aplicația ta de e-mail. Dacă nu s-a deschis, poți scrie direct la hello@acq.studio.';
    location.href = `mailto:hello@acq.studio?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  });
})();
