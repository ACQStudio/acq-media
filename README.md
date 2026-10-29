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

## Domeniu și instalare

DNS: media.acq.ro CNAME acqstudio.github.io. Domeniul acq.ro rămâne la furnizorul său. În GitHub Pages este activată opțiunea Enforce HTTPS.

Invitația de pe Home permite instalarea directă unde browserul oferă această funcție; pe iPhone explică Partajează → Adaugă pe ecranul principal, iar pe Mac pașii din Safari → Adaugă în Dock. Nu apare în modul aplicație și se poate amâna.
