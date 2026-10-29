# ACQ Media — știri pe scurt

Site static în română, cu secțiunile Sport, Hot, News și Music. GitHub Actions citește fluxurile RSS, Gemini selectează și rezumă știrile în română, apoi actualizează paginile și arhiva. Fiecare știre trimite la publicația originală.

## Publicare și automatizare

1. Creează un repository public numit `acq-media` și încarcă toate fișierele din arhivă, inclusiv `.github/workflows/daily.yml`.
2. În `Settings → Actions → General → Workflow permissions`, activează **Read and write permissions**. Acțiunea zilnică salvează arhiva în repository.
3. În `Settings → Pages → Build and deployment`, alege **GitHub Actions** ca sursă.
4. Creează o cheie în [Google AI Studio](https://aistudio.google.com/) și adaug-o în `Settings → Secrets and variables → Actions` cu numele exact `GEMINI_API_KEY`.
5. În fila `Actions`, workflow-ul **Știri zilnice** rulează automat zilnic. La o rulare manuală, lasă opțiunea **Publică fișierele existente, fără apel Gemini** debifată pentru a genera o ediție nouă; bifeaz-o când vrei doar să publici fișierele existente.
6. Domeniul personalizat `media.acq.ro` este deja setat în `scripts/feeds.json` și în `Settings → Pages`.
7. În CyberFolks cPanel, deschide `Zone Editor → Manage` pentru `acq.ro`. Șterge înregistrarea `A` (și orice `AAAA`) pentru `media`, apoi adaugă `CNAME`: nume `media`, destinație `acqstudio.github.io`. Nu schimba înregistrările pentru `acq.ro`.
8. După ce GitHub afișează DNS check successful, activează `Enforce HTTPS` în `Settings → Pages`. cPanelul rămâne doar pentru DNS; fișierele site-ului sunt publicate de GitHub Pages.

> Dacă repository-ul are alt nume decât `acq-media`, workflow-ul folosește automat numele lui pentru adresa GitHub Pages.

Workflow-ul automat rulează zilnic la 05:00 UTC (07:00 în România iarna și 08:00 vara). O rulare de generare trimite un apel Gemini pentru toate secțiunile, setează gândirea modelului la `LOW` și îi acordă până la 180 de secunde. La o eroare temporară de server (`500`, `502`, `503` sau `504`) face cel mult o reîncercare după `Retry-After` sau 5 secunde; în acel caz sunt maximum două apeluri. Nu reîncearcă la `429` sau timeout, pentru că cererea poate să fi fost deja procesată și ar putea consuma din nou cota. Rularea manuală a testului **Gemini API smoke test** consumă încă un apel Gemini. Limitele API depind de model și proiectul din AI Studio; abonamentul Gemini obișnuit nu schimbă automat cotele API. Dacă nu găsește suficiente știri verificate într-o secțiune, afișează starea goală în loc să lase știri vechi să pară noi.

## În proiect

- `index.html`: patru foldere cu aceeași suprafață, titluri colorate discret și mișcare tip Wallet; secțiunile pot fi ascunse din „Personalizează”. Arhiva rămâne separat, la final.
- `arhiva.html`: calendarul zilelor publicate și filtre după secțiune.
- `arhiva/AAAA-LL-ZZ.html`: paginile fiecărei ediții păstrate.
- `scripts/generate.py`: RSS, selecție și rezumare cu Gemini într-un apel; reîncearcă o singură dată doar la o eroare temporară de server.
- `scripts/statics.py`: index, arhivă, metadate și sitemap.

## Setări

- `scripts/feeds.json` conține sursele RSS, modelul Gemini și adresele imaginilor de rezervă.
- Modelul implicit este `gemini-3.8-flash`; se poate schimba prin variabila `GEMINI_MODEL`.
- `use_source_images: false` folosește doar imaginile de rezervă.
- Secretul `GEMINI_API_KEY` se păstrează doar în GitHub Actions Secrets. Nu îl adăuga în fișiere sau commit-uri.
