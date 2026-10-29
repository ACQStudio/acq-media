#!/usr/bin/env python3
"""ACQ: RSS -> selecție și rezumare în română cu Gemini -> actualizează paginile HTML.
Rulare:  GEMINI_API_KEY=... python scripts/generate.py (opțiunea --dry-run nu schimbă fișierele)"""
import os, re, sys, json, time, html, calendar, unicodedata, subprocess, datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).parent))
import statics
from provenance import resolve_original_source

ROOT = Path(__file__).parent
SITE = Path(os.getenv("SITE_DIR", ROOT.parent))
CFG = json.loads((ROOT / "feeds.json").read_text("utf-8"))
MODEL = os.getenv("GEMINI_MODEL", CFG["model"])
N, MIN_OK, MAX_AGE_H = 5, 1, 40
MAX_OUTPUT_TOKENS = 12000
UA = {"User-Agent": "Mozilla/5.0 (compatible; ACQMediaBot/1.0)"}
RSS_CACHE = {}
FEED_TIMEOUT, ARTICLE_TIMEOUT, GEMINI_TIMEOUT = (5, 12), (5, 15), (10, 120)
# Retry transient server responses once; never retry a timeout or a quota error.
GEMINI_5XX_RETRIES = 1
LUNI = "ianuarie februarie martie aprilie mai iunie iulie august septembrie octombrie noiembrie decembrie".split()
HIST_F = ROOT / "data" / "history.json"
USAGE_F = ROOT / "data" / "gemini_usage.json"
MAX_DAILY_GEMINI_REQUESTS = 2
REQUESTS_THIS_RUN = 0
now = dt.datetime.now(ZoneInfo("Europe/Bucharest"))
TODAY_ISO = now.strftime("%Y-%m-%d")
TODAY = f"{now.day} {LUNI[now.month-1]} {now.year}"
HIST = json.loads(HIST_F.read_text()) if HIST_F.exists() else {}
HIST = {u: d for u, d in HIST.items() if d >= (now - dt.timedelta(days=14)).strftime("%Y-%m-%d")}

SLIDE = """  <div class="slide {cls}" data-theme="{theme}">
    <div class="s-bg"><img src="{img}" alt="" onload="this.classList.add('loaded')"/></div><div class="s-mask"></div>
    <div class="s-card">
      <div class="card-top"><span class="card-cat">{cat}</span><span class="card-prog">{i} / {n}</span></div>
      <h2 class="card-hed">{hed}</h2>
      <p class="card-sum">{sum}</p>
      <div class="card-foot">
        <span class="card-meta">{meta}</span>
        <button class="card-read" onclick="openModal({k})">Citește</button>
        <button class="card-next" data-next="{nxt}">{btn} <span class="card-next-icon">→</span></button>
      </div>
    </div>
  </div>
"""
EMPTY_SLIDE = """  <div class="slide sdk" data-theme="dark">
    <div class="s-bg"></div><div class="s-mask"></div>
    <div class="s-card">
      <div class="card-top"><span class="card-cat">{cat}</span><span class="card-prog">Azi</span></div>
      <h2 class="card-hed">Ediția de azi nu este încă disponibilă.</h2>
      <p class="card-sum">Nu avem încă suficiente știri verificate pentru această secțiune. Poți răsfoi edițiile anterioare din arhivă.</p>
      <div class="card-foot"><span class="card-meta">ACQ Media · Știri pe scurt</span><a class="card-next" href="arhiva.html">Deschide arhiva <span class="card-next-icon">→</span></a></div>
    </div>
  </div>"""

class GeminiQuotaError(RuntimeError):
    pass

class GeminiBudgetError(RuntimeError):
    pass

def usage_ledger():
    """The committed reservation survives a cancelled Actions run."""
    if not USAGE_F.exists():
        return {"version": 1, "days": {}}
    try:
        ledger = json.loads(USAGE_F.read_text("utf-8"))
        if ledger.get("version") != 1 or not isinstance(ledger.get("days"), dict):
            raise ValueError("format necunoscut")
        entry = ledger["days"].get(TODAY_ISO, {})
        requests = entry.get("requests", 0)
        if isinstance(requests, bool) or not isinstance(requests, int) or requests < 0:
            raise ValueError("număr de cereri invalid")
        if not isinstance(entry.get("reservations", {}), dict):
            raise ValueError("rezervări invalide")
        for reservation in entry.get("reservations", {}).values():
            slots, used = reservation.get("slots"), reservation.get("used")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (slots, used)) or not 0 <= used <= slots <= MAX_DAILY_GEMINI_REQUESTS:
                raise ValueError("sloturi de rezervare invalide")
        return ledger
    except (ValueError, TypeError, AttributeError) as ex:
        raise GeminiBudgetError(f"Registrul de consum Gemini nu este valid; nu trimit cereri: {ex}") from ex

def usage_entry(ledger):
    return ledger["days"].setdefault(TODAY_ISO, {"requests": 0, "ai_completed": False, "reservations": {}})

def save_usage(ledger):
    USAGE_F.parent.mkdir(parents=True, exist_ok=True)
    temporary = USAGE_F.with_name(f".{USAGE_F.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", "utf-8")
    temporary.replace(USAGE_F)

def reservation_id():
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    return f"{run_id}-{os.getenv('GITHUB_RUN_ATTEMPT', '1')}" if run_id else None

def saved_edition():
    path = ROOT / "data" / "archive" / f"{TODAY_ISO}.json"
    try:
        data = json.loads(path.read_text("utf-8"))
        if isinstance(data, dict) and any(isinstance(data.get(name), list) and data[name] for name in CFG["categories"]):
            return data
    except (OSError, ValueError):
        pass
    return None

def reserve_gemini():
    """Reserve before HTTP; Actions must commit/push this file before generation."""
    ledger = usage_ledger()
    entry = usage_entry(ledger)
    if entry.get("ai_completed") and saved_edition():
        print(f"Ediția AI din {TODAY_ISO} este deja salvată; o refolosesc fără alte cereri Gemini.", flush=True)
        return
    run_id = reservation_id()
    if not run_id:
        raise GeminiBudgetError("Rezervarea Gemini necesită GITHUB_RUN_ID și GITHUB_RUN_ATTEMPT.")
    reservations = entry.setdefault("reservations", {})
    if run_id in reservations:
        print(f"Rezervarea acestei rulări există deja ({reservations[run_id]['state']}); nu o redeschid.", flush=True)
        return
    held = sum(max(0, r["slots"] - r["used"]) for r in reservations.values() if r.get("state") == "reserved")
    slots = max(0, MAX_DAILY_GEMINI_REQUESTS - entry["requests"] - held)
    if entry.get("daily_quota_exhausted") or not slots:
        print(f"Bugetul Gemini din {TODAY_ISO} este folosit sau rezervat; continui fără cereri API.", flush=True)
        return
    reservations[run_id] = {"slots": slots, "used": 0, "state": "reserved", "reserved_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    save_usage(ledger)
    print(f"Am rezervat {slots} cereri Gemini pentru rularea {run_id}. Rezervarea trebuie salvată în main înainte de API.", flush=True)

def has_gemini_reservation():
    entry = usage_entry(usage_ledger())
    reservation = entry.get("reservations", {}).get(reservation_id(), {})
    return not entry.get("daily_quota_exhausted") and reservation.get("state") == "reserved" and reservation.get("used", 0) < reservation.get("slots", 0)

def consume_gemini_request():
    global REQUESTS_THIS_RUN
    if dt.datetime.now(ZoneInfo("Europe/Bucharest")).strftime("%Y-%m-%d") != TODAY_ISO:
        raise GeminiBudgetError("Data Europei/București s-a schimbat după rezervare; nu consum sloturile zilei precedente.")
    ledger = usage_ledger()
    entry = usage_entry(ledger)
    reservation = entry.get("reservations", {}).get(reservation_id(), {})
    if entry.get("daily_quota_exhausted") or reservation.get("state") != "reserved" or reservation.get("used", 0) >= reservation.get("slots", 0) or entry["requests"] >= MAX_DAILY_GEMINI_REQUESTS:
        raise GeminiBudgetError("Nu mai există un slot Gemini rezervat pentru această rulare; nu trimit alte cereri.")
    if os.getenv("GITHUB_ACTIONS") == "true":
        # A failed commit/push must not leave an unprotected API call possible.
        path = USAGE_F.relative_to(ROOT.parent).as_posix()
        saved = subprocess.run(["git", "show", f"origin/main:{path}"], cwd=ROOT.parent, capture_output=True, text=True)
        try:
            remote = json.loads(saved.stdout)["days"][TODAY_ISO]["reservations"][reservation_id()]
            persisted = saved.returncode == 0 and remote.get("state") == "reserved" and remote.get("slots", 0) >= reservation["slots"]
        except (ValueError, KeyError, TypeError, AttributeError):
            persisted = False
        if not persisted:
            raise GeminiBudgetError("Rezervarea nu este salvată în origin/main; nu trimit cererea Gemini.")
    reservation["used"] += 1
    entry["requests"] += 1
    save_usage(ledger)
    REQUESTS_THIS_RUN += 1

def finish_gemini_reservation(ai_completed=False, article_count=0, quota_exhausted=False):
    ledger = usage_ledger()
    entry = usage_entry(ledger)
    reservation = entry.get("reservations", {}).get(reservation_id())
    if reservation and reservation.get("state") == "reserved":
        reservation["state"] = "finished"
        reservation["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    if ai_completed:
        entry.update(ai_completed=True, successful_run_id=os.getenv("GITHUB_RUN_ID"), ai_articles=article_count)
    if quota_exhausted:
        entry["daily_quota_exhausted"] = True
    if reservation or ai_completed or quota_exhausted:
        save_usage(ledger)

def reuse_edition(data):
    print(f"Refolosesc ediția salvată din {TODAY_ISO}; fără apeluri Gemini suplimentare.", flush=True)
    for name, cat in CFG["categories"].items():
        render(name, cat, data.get(name, []))
    statics.run(SITE, CFG, TODAY_ISO, data)

def gemini(prompt, schema, max_output_tokens=MAX_OUTPUT_TOKENS):
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    print(f"Gemini API: folosesc modelul {MODEL} pentru un singur lot.", flush=True)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_output_tokens, "thinkingConfig": {"thinkingLevel": "LOW"},
                                 "responseMimeType": "application/json", "responseSchema": schema}}
    for attempt in range(GEMINI_5XX_RETRIES + 1):
        consume_gemini_request()
        try:
            response = requests.post(
                url,
                json=body,
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                timeout=GEMINI_TIMEOUT,
            )
        except requests.Timeout as ex:
            raise RuntimeError(
                "Gemini nu a trimis răspunsul în 120 de secunde. Cererea poate să fi fost procesată; "
                f"nu o retrimit automat ca să evit un al doilea consum: {ex}"
            ) from ex
        except requests.RequestException as ex:
            raise RuntimeError(f"Gemini nu a răspuns; cererea nu a fost retrimisă: {ex}") from ex

        if response.status_code in (500, 502, 503, 504) and attempt < GEMINI_5XX_RETRIES:
            if not has_gemini_reservation():
                raise GeminiBudgetError("Gemini a răspuns cu o eroare temporară; bugetul zilnic nu permite o nouă cerere.")
            try:
                delay = min(60, max(1, int(response.headers.get("Retry-After", "15"))))
            except ValueError:
                delay = 15
            print(f"Gemini a răspuns HTTP {response.status_code}; reîncerc o singură dată după {delay}s.", flush=True)
            time.sleep(delay)
            continue
        break

    if response.status_code == 429:
        try:
            detail = response.json().get("error", {}).get("message", "")
        except Exception:
            detail = response.text
        low = detail.lower()
        if any(term in low for term in ("perday", "per day", "requests per day", "quota exceeded")):
            raise GeminiQuotaError(f"Limita zilnică Gemini a fost atinsă: {detail}")
        raise RuntimeError(f"Gemini a impus o limită temporară (HTTP 429); cererea nu a fost retrimisă: {detail}")
    if response.status_code >= 500:
        raise RuntimeError(f"Gemini este temporar indisponibil (HTTP {response.status_code}); cererea nu a fost retrimisă.")
    if response.status_code == 401:
        raise RuntimeError("Gemini a respins cheia API (HTTP 401). Verifică secretul GEMINI_API_KEY în repository.")
    if response.status_code == 403:
        raise RuntimeError("Proiectul Gemini nu are acces la API (HTTP 403). Verifică accesul proiectului și eligibilitatea lui în AI Studio.")
    if response.status_code == 404:
        raise RuntimeError(f"Modelul Gemini {MODEL} nu a fost găsit (HTTP 404). Verifică modelul din scripts/feeds.json.")
    if response.status_code == 400:
        raise RuntimeError("Gemini a respins formatul cererii (HTTP 400). Verifică schema JSON și configurarea modelului.")
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as ex:
        raise RuntimeError("Gemini a răspuns cu un JSON invalid.") from ex
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts if part.get("text"))
    if not text:
        raise RuntimeError("Gemini a răspuns fără text; verifică Usage și Rate limits în AI Studio.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as ex:
        raise RuntimeError("Gemini nu a întors JSON-ul cerut; cererea nu a fost retrimisă.") from ex

def rss_img(e):
    for k in ("media_content", "media_thumbnail"):
        for m in e.get(k) or []:
            if m.get("url"): return m["url"]
    for l in e.get("links", []):
        if l.get("type", "").startswith("image"): return l.get("href")

def source_name(feed_url, feed_title):
    host = (urlparse(feed_url).hostname or "").lower()
    known = (
        ("news.soldoutmedia.ro", "Sold Out Media"), ("cancan.ro", "CanCan"),
        ("bbc.co.uk", "BBC"), ("bbc.com", "BBC"), ("theguardian.com", "The Guardian"),
        ("digi24.ro", "Digi24"), ("zf.ro", "Ziarul Financiar"), ("libertatea.ro", "Libertatea"),
        ("nme.com", "NME"), ("pitchfork.com", "Pitchfork"), ("billboard.com", "Billboard"),
        ("skysports.com", "Sky Sports"), ("espn.com", "ESPN"), ("people.com", "People"),
        ("eonline.com", "E! News"), ("euronews.com", "Euronews"),
    )
    for suffix, name in known:
        if host == suffix or host.endswith("." + suffix):
            return name
    return (feed_title or host or feed_url).split(" - ")[0].split(" | ")[0].strip()

def normalized(value):
    text = unicodedata.normalize("NFKD", html.unescape(str(value))).lower()
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c))).strip()

RO_MARKERS = set("despre dupa dintre catre care cum cand unde este sunt fost avea au va vor sa se nu si sau ii il le lor aceste acest aceasta acestia fiecare multe multi mai prin fata potrivit anunta spune arata ajunge primeste ramane publicat publicata publicate zilei zile de din la cu pe anii anul azi ieri acum".split())
EN_MARKERS = set("the and or of to for on as after with from at by is are was were has have had their its his her who what when where why how that which but than into over under against between about says said according following new more most rises fall falls surged declined reports shows showed becomes became years year today yesterday".split())

def is_romanian_text(value, min_markers=1):
    """Respinge textul clar rămas în engleză, ca să nu ajungă pe site ca română."""
    raw = html.unescape(str(value)).lower()
    words = re.findall(r"[a-zăâîșț]+", raw)
    norm_words = [normalized(word) for word in words]
    ro = sum(word in RO_MARKERS for word in norm_words)
    en = sum(word in EN_MARKERS for word in norm_words)
    romanian_diacritics = bool(re.search(r"[ăâîșț]", raw))
    if not words or en > ro:
        return False
    if romanian_diacritics and ro >= min_markers:
        return True
    return ro >= max(2, min_markers) and ro > en

HOT_ENTERTAINMENT = re.compile(r"\b(?:monden\w*|showbiz|entertainment|vedet\w*|celebrit\w*|cantaret\w*|solist\w*|actor\w*|actrit\w*|artist\w*|influencer\w*|divort\w*|nunt\w*|iubit\w*|despart\w*|cupl\w*|casatori\w*)\b")
HOT_GENERAL_NEWS = re.compile(r"\b(?:politic\w*|aleger\w*|parlament\w*|guvern\w*|economie|economic\w*|geopolitic\w*|gaze|gazelor|pret(?:ul|uri|urilor)?|factur\w*|pensi[ei]\w*|tax[ae]\w*|inflati\w*|banc[ai]\w*|energie|energetic\w*|razboi\w*|cutremur\w*|meteo|vremea|horoscop|accident\w*|trafic\w*|actualitate)\b")
MUSIC_SUBJECT = re.compile(r"\b(?:music\w*|muzic\w*|album\w*|single\w*|song\w*|singer\w*|cantaret\w*|solist\w*|rapper\w*|rap|hip.?hop|band\w*|trup[ae]\w*|concert\w*|tour\w*|turne\w*|festival\w*|soundtrack\w*|coloana sonora|grammy\w*|brit awards|spotify|billboard charts|chart\w*|record label\w*|label\w*|casa de discuri|case de discuri|royalt\w*|streaming|songwrit\w*|compozitor\w*|dj|ticketmaster|live nation|licentiere|publishing|melodi\w*|pies[ae]\w*|chitar\w*|tob[ae]\w*|drummer\w*)\b")
MUSIC_ACTIVITY = re.compile(r"\b(?:music\w*|muzic\w*|album\w*|single\w*|song\w*|concert\w*|tour\w*|turne\w*|festival\w*|soundtrack\w*|coloana sonora|grammy\w*|spotify|chart\w*|record label\w*|casa de discuri|case de discuri|royalt\w*|drept\w* de autor|streaming|songwrit\w*|compozitor\w*|ticketmaster|live nation|melodi\w*|pies[ae]\w*)\b")
NEWS_SUBJECT = re.compile(r"\b(?:politic\w*|geopolitic\w*|aleger\w*|electoral\w*|midterms|guvern\w*|parlament\w*|presedint\w*|ministr\w*|diplomat\w*|ambasad\w*|armistiti\w*|razboi\w*|conflict\w*|militar\w*|sabotaj\w*|sanctiun\w*|nato|pentagon\w*|kremlin\w*|trump|putin|zelensk\w*|netanyahu|bolsonaro|georgescu|iran\w*|israel\w*|ucrain\w*|rusia|rusesti|houth\w*|economie|economic\w*|afacer\w*|business|contract\w*|corporat\w*|startup\w*|invest\w*|profit\w*|venit\w*|pierder\w*|listare\w*|burs\w*|actiuni|actionar\w*|fuziun\w*|achiziti\w*|concedier\w*|angajati|banc[ai]\w*|bank\w*|credit\w*|inflati\w*|petrol\w*|gaze|gazelor|energie|energetic\w*|comert\w*|tarif\w*|antitrust|reglement\w*)\b")
NEWS_FOCUSED = re.compile(r"\b(?:politic\w*|geopolitic\w*|aleger\w*|electoral\w*|midterms|guvern\w*|parlament\w*|presedint\w*|ministr\w*|curtea de apel|diplomat\w*|armistiti\w*|razboi\w*|militar\w*|sanctiun\w*|economic\w*|economie|afacer\w*|business|contract\w*|corporat\w*|startup\w*|invest\w*|profit\w*|venit\w*|pierder\w*|listare\w*|burs\w*|actionar\w*|fuziun\w*|achiziti\w*|concedier\w*|angajati|banc[ai]\w*|bank\w*|credit\w*|inflati\w*|petrol\w*|energie|energetic\w*|comert\w*|tarif\w*|antitrust|reglement\w*)\b")
NEWS_ENGLISH = re.compile(r"\b(?:politic\w*|geopolitic\w*|election\w*|electoral\w*|government\w*|parliament\w*|president\w*|minister\w*|legislat\w*|foreign policy|diplomac\w*|diplomat\w*|ceasefire\w*|peace talks|war|warfare|military|conflict\w*|sanction\w*|human rights|united nations|econom\w*|financ\w*|market\w*|invest\w*|business\w*|trade|export\w*|import\w*|tariff\w*|inflation|interest rates?|central bank\w*|budget\w*|tax\w*|debt\w*|stock\w*|shares?|shareholder\w*|corporat\w*|merger\w*|acquisition\w*|earnings|revenue\w*|profit\w*|valuation\w*|ipo|layoffs?|job cuts?|antitrust|regulation\w*)\b")

def relevant(item, section):
    """Filtrează subiectele clar greșite înainte de AI sau de rezerva RSS."""
    topics = " ".join(item.get("topics", []))
    text = normalized(" ".join((item.get("title", ""), item.get("snippet", ""), topics, item.get("link", ""))))
    host = urlparse(item.get("link", "")).hostname or ""
    som = host == "news.soldoutmedia.ro"
    topic_set = {normalized(topic) for topic in item.get("topics", [])}
    if section == "hot":
        if host != "cancan.ro" and not host.endswith(".cancan.ro") and not (som and "entertainment" in topic_set):
            return False
        return not HOT_GENERAL_NEWS.search(text) or bool(HOT_ENTERTAINMENT.search(text))
    if section == "music":
        if som:
            return "muzica" in topic_set or ("entertainment" in topic_set and bool(MUSIC_ACTIVITY.search(text)))
        return bool(MUSIC_SUBJECT.search(text))
    if section == "news":
        if som and topic_set.intersection(("trending", "tech & ai")):
            return bool(NEWS_FOCUSED.search(text) or NEWS_ENGLISH.search(text))
        feed_path = urlparse(item.get("feed_url", "")).path.lower()
        if not som and any(part in feed_path for part in ("business", "politics")):
            return True
        return bool(NEWS_SUBJECT.search(text) or NEWS_ENGLISH.search(text))
    return True

def candidates(cat):
    import requests, feedparser
    cut = time.time() - MAX_AGE_H * 3600
    section = Path(cat.get("file", "")).stem
    def read_feed(feed):
        spec = feed if isinstance(feed, dict) else {"url": feed}
        url = spec.get("url", "")
        wanted = {normalized(topic) for topic in spec.get("categories", [])}
        try:
            if url not in RSS_CACHE:
                response = requests.get(url, headers=UA, timeout=FEED_TIMEOUT)
                response.raise_for_status()
                RSS_CACHE[url] = feedparser.parse(response.content)
            d = RSS_CACHE[url]
        except Exception as ex:
            return url, [], str(ex)
        found = []
        for e in d.entries[:100]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t and calendar.timegm(t) < cut: continue
            link, title = e.get("link"), re.sub(r"\s+", " ", e.get("title", "")).strip()
            if not link or not title: continue
            topics = [str(tag.get("term", "")).strip() for tag in e.get("tags", []) if tag.get("term")]
            if wanted and not wanted.intersection(normalized(topic) for topic in topics): continue
            item = {"title": title, "link": link, "rss_img": rss_img(e), "topics": topics, "feed_url": url,
                        "published_at": calendar.timegm(t) if t else 0,
                        "source": source_name(url, d.feed.get("title", "")),
                        "snippet": re.sub(r"<[^>]+>", "", html.unescape(e.get("summary", "")))[:600]}
            if section and not relevant(item, section): continue
            found.append(item)
            if len(found) == 15: break
        return url, found, None
    feeds = cat["feeds"]
    with ThreadPoolExecutor(max_workers=min(6, len(feeds) or 1)) as pool:
        feed_results = list(pool.map(read_feed, feeds))
    out, seen = [], set()
    for url, found, error in feed_results:
        if error:
            print(f"  ! feed indisponibil {url}: {error}", flush=True)
            continue
        count = 0
        for item in found:
            key = re.sub(r"\W+", "", item["title"].lower())[:60]
            if key in seen or (item["link"] in HIST and HIST[item["link"]] != TODAY_ISO): continue
            seen.add(key)
            out.append(item)
            count += 1
        print(f"  {count:2d} articole noi  <- {url}", flush=True)
    return out

def shortlist(items, limit=N):
    """Păstrează surse diverse fără un apel Gemini separat de selecție."""
    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)
    for group in by_source.values():
        group.sort(key=lambda item: item.get("published_at", 0), reverse=True)
    selected = []
    while len(selected) < limit:
        added = False
        for group in by_source.values():
            if group and len(selected) < limit:
                selected.append(group.pop(0))
                added = True
        if not added:
            break
    return selected

def prepare(c):
    import requests, trafilatura
    text, img = "", c.get("rss_img")
    try:
        response = requests.get(c["link"], headers=UA, timeout=ARTICLE_TIMEOUT)
        response.raise_for_status()
        page = response.text
        if (urlparse(c["link"]).hostname or "").endswith("soldoutmedia.ro"):
            original = resolve_original_source(page, c["link"])
            if not original:
                print(f"  ! omit materialul fără sursă originală identificată: {c['title']}", flush=True)
                return None
            response = requests.get(original["link"], headers=UA, timeout=ARTICLE_TIMEOUT)
            response.raise_for_status()
            page = response.text
            c = {**c, **original}
        text = trafilatura.extract(page, include_comments=False) or ""
        meta = trafilatura.extract_metadata(page)
        img = (meta.image if meta and meta.image else None) or img
    except Exception as ex:
        print(f"  ! articol indisponibil {c['link']}: {ex}", flush=True)
    if len(text) < 700:
        print(f"  ! omit materialul cu prea puțin conținut documentat: {c['title']}", flush=True)
        return None
    return {**c, "img": img, "article_text": text[:3200]}

def prepare_many(items):
    if not items: return []
    with ThreadPoolExecutor(max_workers=min(12, len(items))) as pool:
        prepared = list(pool.map(prepare, items))
    return [item for item in prepared if item]

def write_batch(items):
    if not items: return []
    entries, briefs = [], {}
    for i, c in enumerate(items):
        briefs.setdefault(c["_section"], c["_brief"])
        topics = ", ".join(c.get("topics", []))
        entries.append(f"ID: {i}\nSECȚIUNE: {c['_section']}\nSURSĂ: {c['source']}\nCATEGORII RSS: {topics}\nTITLU ORIGINAL: {c['title']}\nTEXT: {c['article_text']}")
    category_labels = ["Sport", "Fotbal", "Tenis", "Formula 1", "Monden", "Vedete", "Politică", "Geopolitică", "Afaceri", "Economie", "Știri", "Muzică", "Artiști", "Concerte", "Industrie muzicală"]
    schema = {"type": "OBJECT", "properties": {"articles": {"type": "ARRAY", "maxItems": len(items), "items": {
        "type": "OBJECT", "properties": {"id": {"type": "INTEGER"}, "skip": {"type": "BOOLEAN"},
        "cat": {"type": "STRING", "enum": category_labels}, "hed": {"type": "STRING"}, "sum": {"type": "STRING"},
        "body": {"type": "ARRAY", "items": {"type": "STRING"}}},
        "required": ["id", "skip", "cat", "hed", "sum", "body"]}}},
        "required": ["articles"]}
    prompt = (
        "Ești redactor la un site de știri în limba română. Primești texte numerotate din mai multe secțiuni. "
        f"Alege până la {N} știri distincte, relevante și susținute clar pentru fiecare secțiune. Nu trebuie să fie {N}: păstrează doar câte merită publicate, chiar zero. "
        "Nu completa lista cu subiecte marginale, duplicate sau care țin de altă secțiune. Hot înseamnă cancan/showbiz, iar Muzică înseamnă muzică și industria sa. "
        "Nu amesteca secțiunile și nu combina articole. "
        "Returnează articolele în ordinea importanței din fiecare secțiune. Pentru fiecare ID întoarce id, skip, cat, hed, sum și body. "
        "Pentru o știre publicabilă, skip=false și completează toate câmpurile. Pentru una insuficient documentată, skip=true, cat/hed/sum goale și body gol. "
        "Scrie în română TOATE câmpurile publicate: eticheta, titlul, rezumatul și paragrafele. Nu lăsa text în engleză; păstrează nemodificate doar numele proprii și mărcile. "
        "Redă în română faptele din surse în alte limbi, cu formulări proprii; nu traduce mot-a-mot și nu copia fraze. "
        "Folosește EXCLUSIV faptele din text. Nu inventa nume, cifre, date sau citate. "
        "Atribuie explicit sursei acuzațiile și declarațiile controversate. Ton neutru. "
        "Pentru cat alege strict una dintre etichetele românești din schemă; hed = titlu de maximum 95 de caractere; "
        "sum = rezumat de 1-2 propoziții, 25-35 de cuvinte; body = 3 paragrafe, aproximativ 100-160 de cuvinte în total. "
        "Corpul trebuie să dezvolte știrea: ce s-a întâmplat, detaliile concrete disponibile și contextul relevant din sursă. "
        "Nu repeta doar rezumatul și nu adăuga formule despre fluxul RSS, accesarea sursei sau lipsa informațiilor. "
        "Dacă textul-sursă nu susține cel puțin 3 paragrafe informative, marchează skip=true. "
        "Păstrează ID-ul fiecărui text și nu combina informații din articole diferite.\n\nSECȚIUNI:\n"
        + "\n".join(f"{section}: {brief}" for section, brief in briefs.items())
        + "\n\nTEXTE:\n" + "\n\n---\n\n".join(entries)
    )
    output_limit = min(MAX_OUTPUT_TOKENS, max(2048, 512 + len(items) * 600))
    result = gemini(prompt, schema, max_output_tokens=output_limit)
    if not isinstance(result, dict) or not isinstance(result.get("articles"), list):
        raise RuntimeError("Gemini nu a întors lista de articole cerută.")
    by_id, ordered_ids = {}, []
    returned = result.get("articles", [])
    skipped = sum(1 for article in returned if isinstance(article, dict) and article.get("skip") is True)
    for article in returned:
        if not isinstance(article, dict):
            continue
        i = article.get("id")
        if isinstance(i, bool) or not isinstance(i, int) or i < 0 or i >= len(items) or i in by_id or article.get("skip"):
            continue
        if not all(isinstance(article.get(key), str) and article[key].strip() for key in ("cat", "hed", "sum")):
            continue
        if article["cat"] not in category_labels or not is_romanian_text(article["hed"] + " " + article["sum"], min_markers=3):
            print(f"  ! resping rezultatul {i}: eticheta sau titlul nu este în română", flush=True)
            continue
        if not isinstance(article.get("body"), list) or not 3 <= len(article["body"]) <= 4 or not all(isinstance(p, str) and p.strip() for p in article["body"]):
            continue
        if not 70 <= len(" ".join(article["body"]).split()) <= 220:
            print(f"  ! resping rezultatul {i}: conținut prea scurt sau prea lung", flush=True)
            continue
        if not is_romanian_text(article["sum"], min_markers=2) or not is_romanian_text(" ".join(article["body"]), min_markers=3):
            print(f"  ! resping rezultatul {i}: rezumatul sau conținutul nu este în română", flush=True)
            continue
        c = items[i]
        by_id[i] = {**article, "source": c["source"], "link": c["link"], "img": c["img"], "_section": c["_section"]}
        ordered_ids.append(i)
    print(f"Gemini: a analizat {len(items)} texte, a returnat {len(returned)} rezultate, a marcat {skipped} ca skip și a validat {len(by_id)}.", flush=True)
    return [by_id[i] for i in ordered_ids]

def render(name, cat, items):
    e, n, slides, art = html.escape, len(items), [], []
    fb = cat["fallback_images"]
    for k, it in enumerate(items):
        dark = k % 2 == 0
        img = it["img"] if CFG["use_source_images"] and it.get("img") else fb[k % len(fb)]
        slides.append(SLIDE.format(cls="sdk" if dark else "slt", theme="dark" if dark else "light", img=e(img), cat=e(it["cat"]),
            i=k + 1, n=n, hed=e(it["hed"]), sum=e(it["sum"]), meta=e(f"{TODAY} · {it['source']}"), k=k, nxt=k + 1,
            btn="Încheie ediția" if k == n - 1 else "Următoarea știre"))
        body = "".join(f"<p>{e(p)}</p>" for p in it["body"])
        art.append({"tag": it["cat"], cat["meta_key"]: f"{TODAY} · Sursa: {it['source']}", "hed": it["hed"], "body": body})
    if not slides:
        label = {"sport": "Sport", "hot": "Hot", "news": "Știri", "music": "Muzică"}.get(name, "Știri")
        slides.append(EMPTY_SLIDE.format(cat=html.escape(label)))
    f = SITE / cat["file"]; t = f.read_text("utf-8")
    t = re.sub(r"<!--SLIDES-->.*?<!--/SLIDES-->", lambda m: "<!--SLIDES-->\n" + "\n".join(slides) + "\n  <!--/SLIDES-->", t, flags=re.S)
    aj = json.dumps(art, ensure_ascii=False).replace("</", "<\\/")
    t = re.sub(r"/\*ART\*/.*?/\*/ART\*/", lambda m: "/*ART*/" + aj + "/*/ART*/", t, flags=re.S)
    f.write_text(t, "utf-8")

def main():
    rss_only = "--rss-only" in sys.argv
    if "--dry-run" in sys.argv:
        print("Dry-run: nu am date de probă incluse, așa că nu fac cereri și nu modific fișiere.")
        return
    if "--reserve-gemini" in sys.argv:
        reserve_gemini()
        return
    existing_edition = saved_edition()
    if rss_only:
        if existing_edition:
            reuse_edition(existing_edition)
        else:
            print("Fără API: păstrez ediția publicată; nu o înlocuiesc cu titluri sau fragmente RSS.", flush=True)
        return
    entry = usage_entry(usage_ledger())
    if entry.get("ai_completed") and existing_edition:
        reuse_edition(existing_edition)
        return
    api_allowed = has_gemini_reservation() if not rss_only else False
    if not rss_only and not api_allowed and existing_edition:
        reuse_edition(existing_edition)
        return
    ok_any, done, all_candidates = False, {}, []
    for name, cat in CFG["categories"].items():
        print(f"\n== {name}", flush=True)
        try:
            available = candidates(cat)
            suitable = [item for item in available if relevant(item, name)]
            selected = shortlist(suitable, N)
            print(f"  {len(available)} candidați RSS; {len(suitable)} se potrivesc secțiunii; selectez maximum {len(selected)}", flush=True)
            for item in selected:
                all_candidates.append({**item, "_section": name, "_brief": cat["brief"]})
        except Exception as ex:
            print(f"  ! eroare la colectarea știrilor: {ex}", flush=True)
    if rss_only:
        prepared = [{**item, "img": item.get("rss_img"), "article_text": item.get("snippet", "")} for item in all_candidates]
    else:
        prepared = prepare_many(all_candidates)
    if rss_only:
        print(f"\n{len(prepared)} titluri RSS disponibile; nu trimit cereri Gemini.", flush=True)
    else:
        print(f"\n{len(prepared)} texte disponibile; redactez până la {N} știri relevante pe secțiune într-un singur apel Gemini", flush=True)
    generated, ai_completed, budget_blocked, quota_exhausted = [], False, False, False
    api_key = os.getenv("GEMINI_API_KEY")
    if prepared and rss_only:
        print("Rulare RSS-only: nu apelez Gemini; public titlurile și linkurile surselor.", flush=True)
    elif prepared and api_key and api_allowed:
        try:
            generated = write_batch(prepared)
            ai_completed = True
            print(f"Gemini: {REQUESTS_THIS_RUN} cereri în această rulare; {len(generated)} știri validate în total", flush=True)
        except GeminiQuotaError as ex:
            quota_exhausted = True
            print(f"\n! {ex}\n! Păstrez ediția publicată fără alte apeluri Gemini.", flush=True)
        except GeminiBudgetError as ex:
            budget_blocked = True
            print(f"\n! {ex}\n! Păstrez ediția existentă dacă este disponibilă.", flush=True)
        except Exception as ex:
            print(f"\n! Gemini nu a putut redacta ediția: {ex}\n! Păstrez ediția publicată, fără alte apeluri Gemini.", flush=True)
    elif prepared and api_key:
        print("! Nu există o rezervare Gemini disponibilă; păstrez ediția publicată fără API.", flush=True)
    elif prepared:
        print("! GEMINI_API_KEY lipsește; păstrez ediția publicată fără apel Gemini.", flush=True)

    if not generated:
        finish_gemini_reservation(quota_exhausted=quota_exhausted)
        if existing_edition:
            reuse_edition(existing_edition)
        else:
            print("Nu există o ediție nouă completă; paginile publicate rămân disponibile.", flush=True)
        return

    for name, cat in CFG["categories"].items():
        items = [dict(item) for item in generated if item.get("_section") == name][:N]
        if not rss_only:
            print(f"  Gemini a validat {len(items)} știri pentru {name}", flush=True)
        for item in items:
            item.pop("_section", None)
        if len(items) < MIN_OK:
            print(f"  ! {name}: doar {len(items)} știri bune -> afișez mesajul de ediție indisponibilă", flush=True)
            render(name, cat, []); continue
        for it in items: print(f"  + {it['hed'][:80]}", flush=True)
        render(name, cat, items); ok_any = True; done[name] = items
        for it in items: HIST[it["link"]] = TODAY_ISO
    HIST_F.parent.mkdir(exist_ok=True); HIST_F.write_text(json.dumps(HIST, indent=0))
    statics.run(SITE, CFG, TODAY_ISO, done)
    finish_gemini_reservation(ai_completed=ai_completed and bool(generated), article_count=len(generated), quota_exhausted=quota_exhausted)
    if not ok_any:
        print("\nNu s-au găsit suficiente știri verificate într-o secțiune; site-ul a fost actualizat cu starea ediției.", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()
