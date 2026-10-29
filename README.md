# ACQ Media — știri pe scurt

Site static în limba română, cu patru secțiuni: **Sport**, **Hot** (CanCan și showbiz), **Știri** (politică, geopolitică și afaceri) și **Muzică** (muzică și industria divertismentului). Fiecare ediție poate include până la cinci știri relevante în fiecare secțiune; dacă nu sunt cinci știri potrivite și verificate, publică mai puține. Fiecare știre trimite la sursa originală.

Prima pagină are patru foldere închise la culoare, cu textură discretă și numele secțiunii gravat. Site-ul se adaptează la telefon și desktop și poate fi instalat pe ecranul principal.

## Publicare și automatizare

1. Repository-ul trebuie să fie public și să conțină fișierul `.github/workflows/daily.yml`.
2. În **Settings → Actions → General → Workflow permissions**, activează **Read and write permissions**. Acțiunea zilnică salvează articolele și arhiva în repository.
3. În **Settings → Pages → Build and deployment**, alege **GitHub Actions** ca sursă.
4. În **Settings → Secrets and variables → Actions**, adaugă secretul `GEMINI_API_KEY`. Cheia rămâne numai în GitHub Actions Secrets.
5. Pentru ediția nouă, deschide **Actions → Știri zilnice → Run workflow** și lasă debifată opțiunea „Doar republică fișierele existente, fără generare AI”. Pentru publicarea designului existent, bifeaz-o.
6. Workflow-ul zilnic rulează la **04:30, ora Europei/București**. Poate porni cu întârziere când GitHub Actions este aglomerat.
7. Domeniul configurat este `media.acq.ro`. DNS-ul trebuie să aibă `CNAME media → acqstudio.github.io`; înregistrările pentru `acq.ro` rămân neschimbate. După validarea DNS, activează **Enforce HTTPS** în **Settings → Pages**.

## Cum generează ediția

- Citește fluxurile RSS din `scripts/feeds.json`, elimină duplicatele și știrile nepotrivite secțiunii.
- Pregătește cel mult cinci articole pe secțiune și face un singur apel Gemini pentru întregul lot.
- Modelul implicit este `gemini-3.5-flash-lite`, configurabil prin `GEMINI_MODEL`. Un răspuns Gemini este verificat pentru câmpuri complete și text în română înainte de publicare.
- La o eroare temporară de server (`500`, `502`, `503` sau `504`), poate încerca încă o dată; un singur lot înseamnă maximum două cereri API. Nu retrimite automat un timeout sau o eroare de cotă.
- Dacă Gemini nu răspunde, publică cel mult cinci fragmente RSS numai când titlul și fragmentul sunt în română. Dacă nu există material românesc suficient, secțiunea spune că ediția nu este disponibilă; nu completează cu text inventat sau în engleză.
- **Actualizează titlurile din RSS fără AI** publică fluxurile fără apeluri Gemini. Este declanșat de modificarea surselor RSS și se poate porni manual din Actions.
- Schimbările de design publică site-ul existent, fără să consume apeluri Gemini. Un test Gemini separat nu este necesar: rularea manuală a ediției zilnice face cel mult un apel pe lot.

## Fișiere principale

- `index.html`, `home.css`: pagina Home și folderele secțiunilor.
- `site-ui.css`, `site-ui.js`, `manifest.webmanifest`, `sw.js`: aspectul comun, instalarea și funcțiile offline.
- `scripts/feeds.json`: adrese RSS, model Gemini și `site_url`.
- `scripts/generate.py`: colectarea RSS, filtrarea, redactarea în română și verificarea textului.
- `scripts/statics.py`: calendarul, arhiva, metadatele și sitemap-ul.
- `scripts/save_edition.sh`: salvează ediția și sincronizează în siguranță `main`.
- `.github/workflows/daily.yml`: ediția zilnică și publicarea.
- `.github/workflows/rss-only.yml`: publicarea RSS fără AI.

Cheia Gemini se păstrează doar în GitHub Secrets. Abonamentul Gemini pentru aplicația Gemini nu include automat credit sau limite API în AI Studio.
