# ACQ Media

Site de știri în română, publicat la https://media.acq.ro prin GitHub Pages.

## Ediția zilnică

Workflow-ul „Știri zilnice” rulează la 04:30, Europe/Bucharest. GitHub poate întârzia pornirea programată.

Generatorul citește fluxurile configurate în scripts/feeds.json. News are ca țintă zece articole din politică, geopolitică, afaceri, finanțe și inteligență artificială. Sport, Hot și Music au câte patru sau cinci subiecte, în funcție de materialele documentate. Pentru materialele descoperite prin Sold Out Media urmărește linkul explicit al publicației originale.

Un singur lot Gemini redactează titlurile, rezumatele și articolele în română. Fiecare articol are trei paragrafe, aproximativ 100–160 de cuvinte, și mențiunea discretă a publicației de origine. Nu se completează ediția cu titluri ori fragmente RSS. Dacă serviciul AI nu răspunde, se păstrează ediția existentă.

## Plafonul API

Model: gemini-3.5-flash-lite. Maximum două cereri Gemini pe zi, pentru întregul site. În mod normal este suficientă una. Se poate retrimite o singură dată numai la răspunsuri 5xx și numai dacă mai există un slot zilnic. Nu se repetă timeout-urile sau erorile 429.

Înainte de API, workflow-ul rezervă sloturile în scripts/data/gemini_usage.json și le salvează în main. Generatorul verifică rezervarea salvată înainte de HTTP. O rulare anulată păstrează conservator sloturile rezervate până a doua zi. După o ediție AI reușită, reluarea workflow-ului refolosește ediția fără alte apeluri.

Plafonul aparține acestui repository; alte aplicații care folosesc același proiect Google au consum separat. Cota gratuită și facturarea se verifică în Google AI Studio pentru proiectul cheii. Cheia rămâne numai în secretul GitHub GEMINI_API_KEY.

## Publicare manuală

Actions → Știri zilnice → Run workflow. Bifează „Doar republică fișierele existente” când vrei să publici designul fără generare. Un push obișnuit publică numai fișierele. Un commit marcat [testeaza-gemini] trece prin același plafon zilnic și aceleași rezervări.

## Postări pentru rețele sociale

Galeria ACQ Studio este publicată separat, cu acces privat prin contul proprietarului în ChatGPT. Preia cea mai recentă ediție salvată și pregătește imaginile și descrierile pentru descărcare și publicare manuală. Nu solicită acces la conturile sociale și nu face apeluri Gemini suplimentare. Data afișată este data reală a ediției, inclusiv atunci când site-ul a păstrat o ediție mai veche.

Exportul Instagram pregătește imagini pătrate de 1080 × 1080, cu fotografia întreagă, și descrieri cu hashtaguri în funcție de subiect. Pentru export local, instalează `pip install -r scripts/requirements-social.txt` și rulează `python scripts/export_instagram.py --output /cale/noua/acq-instagram`. Folosește Python 3.12 și fonturi DejaVu Sans pe Linux sau Arial pe macOS.

## Domeniu și instalare

CyberFolks verifică versiunea din GitHub la fiecare cinci minute.

Invitația de pe Home și din secțiuni permite instalarea directă unde browserul oferă această funcție; pe iPhone explică Partajează → Adaugă pe ecranul principal, iar pe Mac pașii din Safari → Adaugă în Dock. Nu apare în modul aplicație și se poate amâna.

## Publicitate

Fiecare secțiune cu cel puțin două articole include un singur ecran de publicitate după al doilea articol, în aceeași derulare. Ecranul nu este numărat ca știre și nu schimbă articolul deschis prin link direct.

Butonul deschide contact.html cu secțiunea preselectată. Formularul pregătește un mesaj către media@acq.ro, adresa ACQ Media. „Continuă în e-mail” deschide aplicația de e-mail; vizitatorul trimite mesajul de acolo. Site-ul nu afișează o confirmare falsă de livrare și nu stochează datele formularului.
