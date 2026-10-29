# ACQ Media

Site de știri în română, publicat la https://media.acq.ro prin GitHub Pages.

## Ediția zilnică

Workflow-ul „Știri zilnice” rulează la 04:30, Europe/Bucharest. GitHub poate întârzia pornirea programată.

Generatorul citește fluxurile configurate în scripts/feeds.json, selectează până la cinci subiecte relevante pe secțiune și extrage textul articolelor. Pentru materialele descoperite prin Sold Out Media urmărește linkul explicit al publicației originale. Omite materialele fără sursă identificabilă sau fără suficient text.

Un singur lot Gemini redactează titlurile, rezumatele și articolele în română. Fiecare articol are trei paragrafe, aproximativ 100–160 de cuvinte, și mențiunea discretă a publicației de origine. Nu se completează ediția cu titluri ori fragmente RSS. Dacă serviciul AI nu răspunde, se păstrează ediția existentă.

## Plafonul API

Model: gemini-3.5-flash-lite. Maximum două cereri Gemini pe zi, pentru întregul site. În mod normal este suficientă una. Se poate retrimite o singură dată numai la răspunsuri 5xx și numai dacă mai există un slot zilnic. Nu se repetă timeout-urile sau erorile 429.

Înainte de API, workflow-ul rezervă sloturile în scripts/data/gemini_usage.json și le salvează în main. Generatorul verifică rezervarea salvată înainte de HTTP. O rulare anulată păstrează conservator sloturile rezervate până a doua zi. După o ediție AI reușită, reluarea workflow-ului refolosește ediția fără alte apeluri.

Plafonul aparține acestui repository; alte aplicații care folosesc același proiect Google au consum separat. Cota gratuită și facturarea se verifică în Google AI Studio pentru proiectul cheii. Cheia rămâne numai în secretul GitHub GEMINI_API_KEY.

## Publicare manuală

Actions → Știri zilnice → Run workflow. Bifează „Doar republică fișierele existente” când vrei să publici designul fără generare. Un push obișnuit publică numai fișierele. Un commit marcat [testeaza-gemini] trece prin același plafon zilnic și aceleași rezervări.

## Postări Instagram

După publicarea site-ului, workflow-ul pregătește automat câte o grafică ACQ de 1080 × 1350 și o descriere în română pentru fiecare știre completă din cea mai recentă ediție. Grafica include titlul integral, rezumatul, secțiunea, sursa și data ediției. Descrierea reutilizează cele trei paragrafe redactate pentru site, cu sursa și câteva hashtaguri ale secțiunii. Nu se fac apeluri AI suplimentare și nu este necesar acces la contul Instagram.

Descarcă pachetul din **Actions → Știri zilnice → rularea terminată → Artifacts → acq-instagram-AAAA-LL-ZZ**. Fiecare PNG are alături un TXT cu același nume: încarci imaginea și copiezi descrierea în Instagram. Pachetele sunt păstrate 14 zile. Pentru a reface pachetul fără un nou apel Gemini, rulează workflow-ul cu **„Doar republică fișierele existente”** bifat.

Data din pachet este data reală a ediției. Dacă generatorul a păstrat o ediție mai veche, exportul nu o prezintă drept știri noi. Fișierele sunt pregătite temporar pe runner și publicate doar ca artifact, nu în site sau în istoricul Git. Publicarea site-ului se termină înaintea jobului Instagram.

Export local: `pip install -r scripts/requirements-social.txt`, apoi `python scripts/export_instagram.py --output /cale/noua/acq-instagram`. Python 3.12 și fonturi DejaVu Sans pe Linux sau Arial pe macOS; se pot indica alte fonturi cu `--font-regular` și `--font-bold`.

## Domeniu și instalare

DNS: media.acq.ro CNAME acqstudio.github.io. Domeniul acq.ro rămâne la furnizorul său. În GitHub Pages este activată opțiunea Enforce HTTPS.

Invitația de pe Home permite instalarea directă unde browserul oferă această funcție; pe iPhone explică Partajează → Adaugă pe ecranul principal, iar pe Mac pașii din Safari → Adaugă în Dock. Nu apare în modul aplicație și se poate amâna.

## Publicitate

Fiecare secțiune cu cel puțin două articole include un singur ecran de publicitate după al doilea articol, în aceeași derulare. Ecranul nu este numărat ca știre și nu schimbă articolul deschis prin link direct.

Butonul deschide contact.html cu secțiunea preselectată. Formularul pregătește un mesaj către hello@acq.studio, adresa publică folosită și pe acq.ro. „Continuă în e-mail” deschide aplicația de e-mail; vizitatorul trimite mesajul de acolo. Site-ul nu afișează o confirmare falsă de livrare și nu stochează datele formularului.
