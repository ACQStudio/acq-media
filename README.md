# ACQ Media — știri pe scurt

Site static în română, cu secțiunile Sport, Hot, News și Music. GitHub Actions citește fluxurile RSS, Gemini selectează și rezumă știrile în română, apoi actualizează paginile și arhiva. Fiecare știre trimite la publicația originală.

## Publicare și automatizare

1. Creează un repository public numit `acq-media` și încarcă toate fișierele din arhivă, inclusiv `.github/workflows/daily.yml`.
2. În `Settings → Actions → General → Workflow permissions`, activează **Read and write permissions**. Acțiunea zilnică salvează arhiva în repository.
3. În `Settings → Pages → Build and deployment`, alege **GitHub Actions** ca sursă.
4. Creează o cheie în [Google AI Studio](https://aistudio.google.com/) și adaug-o în `Settings → Secrets and variables → Actions` cu numele exact `GEMINI_API_KEY`.
5. Din fila `Actions`, rulează manual workflow-ul **Știri zilnice**. Acesta detectează adresa repository-ului, generează ediția, salvează arhiva și publică site-ul.
6. Dacă folosești un domeniu propriu, adaugă adresa lui în `site_url` din `scripts/feeds.json` și configurează domeniul la `Settings → Pages`.

> Dacă repository-ul are alt nume decât `acq-media`, workflow-ul folosește automat numele lui pentru adresa GitHub Pages.

Workflow-ul automat rulează zilnic la 05:00 UTC (07:00 în România iarna și 08:00 vara). Dacă nu găsește cel puțin trei știri verificate într-o secțiune, afișează un mesaj în acea secțiune în loc să lase știri vechi să pară noi. Dacă nu găsește știri în nicio secțiune, publică starea actuală și încearcă din nou a doua zi.

## În proiect

- `index.html`: patru foldere colorate cu știri din ediția zilei; secțiunile pot fi ascunse din „Personalizează”. Arhiva rămâne separat, la final.
- `arhiva.html`: calendarul zilelor publicate și filtre după secțiune.
- `arhiva/AAAA-LL-ZZ.html`: paginile fiecărei ediții păstrate.
- `scripts/generate.py`: RSS, selecție și rezumare cu Gemini.
- `scripts/statics.py`: index, arhivă, metadate și sitemap.

## Setări

- `scripts/feeds.json` conține sursele RSS, modelul Gemini și adresele imaginilor de rezervă.
- Modelul implicit este `gemini-3.8-flash`; se poate schimba prin variabila `GEMINI_MODEL`.
- `use_source_images: false` folosește doar imaginile de rezervă.
- Secretul `GEMINI_API_KEY` se păstrează doar în GitHub Actions Secrets. Nu îl adăuga în fișiere sau commit-uri.
