#!/usr/bin/env python3
"""ACQ: RSS -> selecție și rezumare în română cu Gemini -> actualizează paginile HTML.
Rulare:  GEMINI_API_KEY=... python scripts/generate.py (opțiunea --dry-run nu schimbă fișierele)"""
import os, re, sys, json, time, html, calendar, datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent))
import statics

ROOT = Path(__file__).parent
SITE = Path(os.getenv("SITE_DIR", ROOT.parent))
CFG = json.loads((ROOT / "feeds.json").read_text("utf-8"))
MODEL = os.getenv("GEMINI_MODEL", CFG["model"])
N, MIN_OK, MAX_AGE_H = 5, 3, 40
UA = {"User-Agent": "Mozilla/5.0 (compatible; ACQMediaBot/1.0)"}
FEED_TIMEOUT, ARTICLE_TIMEOUT, GEMINI_TIMEOUT = (5, 12), (5, 15), 90
LUNI = "ianuarie februarie martie aprilie mai iunie iulie august septembrie octombrie noiembrie decembrie".split()
HIST_F = ROOT / "data" / "history.json"
now = dt.datetime.now(ZoneInfo("Europe/Bucharest"))
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

def gemini(prompt, schema):
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 8192, "responseMimeType": "application/json", "responseSchema": schema}}
    for a in range(3):
        try:
            r = requests.post(url, json=body, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=GEMINI_TIMEOUT)
        except requests.RequestException as ex:
            if a == 2: raise
            wait = 5 * (a + 1)
            print(f"  ! Gemini nu răspunde; reiau peste {wait}s: {ex}", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429:
            try:
                detail = r.json().get("error", {}).get("message", "")
            except Exception:
                detail = r.text
            low = detail.lower()
            if any(term in low for term in ("perday", "per day", "requests per day", "quota exceeded")):
                raise GeminiQuotaError(f"Limita zilnică Gemini a fost atinsă: {detail}")
        if r.status_code in (429, 500, 503):
            if a == 2: r.raise_for_status()
            wait = 5 * (a + 1)
            print(f"  ! Gemini a răspuns cu {r.status_code}; reiau peste {wait}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    raise RuntimeError("Gemini indisponibil")

def rss_img(e):
    for k in ("media_content", "media_thumbnail"):
        for m in e.get(k) or []:
            if m.get("url"): return m["url"]
    for l in e.get("links", []):
        if l.get("type", "").startswith("image"): return l.get("href")

def candidates(cat):
    import requests, feedparser
    cut = time.time() - MAX_AGE_H * 3600
    def read_feed(url):
        try:
            response = requests.get(url, headers=UA, timeout=FEED_TIMEOUT)
            response.raise_for_status()
            d = feedparser.parse(response.content)
        except Exception as ex:
            return url, [], str(ex)
        found = []
        for e in d.entries[:15]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t and calendar.timegm(t) < cut: continue
            link, title = e.get("link"), re.sub(r"\s+", " ", e.get("title", "")).strip()
            if not link or not title: continue
            found.append({"title": title, "link": link, "rss_img": rss_img(e),
                          "source": (d.feed.get("title", "") or url.split("/")[2]).split(" - ")[0].split(" | ")[0].strip(),
                          "snippet": re.sub(r"<[^>]+>", "", html.unescape(e.get("summary", "")))[:600]})
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
            if key in seen or item["link"] in HIST: continue
            seen.add(key)
            out.append(item)
            count += 1
        print(f"  {count:2d} articole noi  <- {url}", flush=True)
    return out

def pick(cat, cands):
    if not cands: return []
    cands = cands[:45]
    lst = "\n".join(f"{i}. [{c['source']}] {c['title']} — {c['snippet'][:160]}" for i, c in enumerate(cands))
    r = gemini(f"Ești redactor-șef la un site de știri minimalist în limba română. Secțiunea: {cat['brief']}\n"
               f"Din lista de mai jos alege cele {N+3} cele mai importante și mai diverse știri (fără două despre același eveniment), "
               f"în ordinea importanței. Returnează doar indicii.\n\n{lst}",
               {"type": "OBJECT", "properties": {"ids": {"type": "ARRAY", "items": {"type": "INTEGER"}}}, "required": ["ids"]})
    return [cands[i] for i in dict.fromkeys(r["ids"]) if isinstance(i, int) and 0 <= i < len(cands)]

def prepare(c):
    import requests, trafilatura
    text, img = "", c.get("rss_img")
    try:
        response = requests.get(c["link"], headers=UA, timeout=ARTICLE_TIMEOUT)
        response.raise_for_status()
        page = response.text
        text = trafilatura.extract(page, include_comments=False) or ""
        meta = trafilatura.extract_metadata(page)
        img = (meta.image if meta and meta.image else None) or img
    except Exception as ex:
        print(f"  ! articol indisponibil {c['link']}: {ex}", flush=True)
    if len(text) < 600: text = c["snippet"]
    if len(text) < 200: return None
    return {**c, "img": img, "article_text": text[:7000]}

def prepare_many(items):
    if not items: return []
    with ThreadPoolExecutor(max_workers=min(6, len(items))) as pool:
        prepared = list(pool.map(prepare, items))
    return [item for item in prepared if item]

def write_batch(items):
    if not items: return []
    entries = [f"ID: {i}\nSURSĂ: {c['source']}\nTITLU ORIGINAL: {c['title']}\nTEXT: {c['article_text']}" for i, c in enumerate(items)]
    schema = {"type": "OBJECT", "properties": {"articles": {"type": "ARRAY", "items": {
        "type": "OBJECT", "properties": {"id": {"type": "INTEGER"}, "skip": {"type": "BOOLEAN"},
        "cat": {"type": "STRING"}, "hed": {"type": "STRING"}, "sum": {"type": "STRING"},
        "body": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["id", "skip"]}}},
        "required": ["articles"]}
    prompt = (
        "Ești redactor la un site de știri în limba română. Primești mai multe texte numerotate. "
        "Alege cel mult 5 știri distincte, importante și susținute clar de text. Pentru fiecare ID întoarce un obiect cu acel id și skip. "
        "Pentru o știre publicabilă, skip=false și completează toate câmpurile; pentru una insuficient documentată, skip=true. "
        "Scrie original, cu propriile cuvinte; nu copia și nu traduce fraze. Folosește EXCLUSIV faptele din text. Nu inventa nume, cifre, date sau citate. "
        "Atribuie explicit sursei acuzațiile și declarațiile controversate. Ton neutru. "
        "Câmpuri pentru știrile publicabile: cat = etichetă de 1-3 cuvinte; hed = titlu de maximum 110 caractere; "
        "sum = rezumat de 2-3 propoziții, 35-55 de cuvinte; body = 3-4 paragrafe, fiecare de 2-4 propoziții. "
        "Păstrează ID-ul fiecărui text și nu combina informații din articole diferite.\n\n" + "\n\n---\n\n".join(entries)
    )
    result = gemini(prompt, schema)
    by_id = {}
    for article in result.get("articles", []):
        i = article.get("id")
        if not isinstance(i, int) or i < 0 or i >= len(items) or article.get("skip"): continue
        if not (article.get("hed") and article.get("sum") and article.get("body")): continue
        c = items[i]
        by_id[i] = {**article, "source": c["source"], "link": c["link"], "img": c["img"]}
    return [by_id[i] for i in range(len(items)) if i in by_id][:N]

def render(name, cat, items):
    e, n, slides, art = html.escape, len(items), [], []
    fb = cat["fallback_images"]
    for k, it in enumerate(items):
        dark = k % 2 == 0
        img = it["img"] if CFG["use_source_images"] and it.get("img") else fb[k % len(fb)]
        slides.append(SLIDE.format(cls="sdk" if dark else "slt", theme="dark" if dark else "light", img=e(img), cat=e(it["cat"]),
            i=k + 1, n=n, hed=e(it["hed"]), sum=e(it["sum"]), meta=e(f"{TODAY} · {it['source']}"), k=k, nxt=k + 1,
            btn="Încheie ediția" if k == n - 1 else "Următoarea știre"))
        body = "".join(f"<p>{e(p)}</p>" for p in it["body"]) + \
               f'<p><a href="{e(it["link"])}" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline">Citește articolul original la {e(it["source"])} ↗</a></p>'
        art.append({"tag": it["cat"], cat["meta_key"]: f"{TODAY} · Sursa: {it['source']}", "hed": it["hed"], "body": body})
    if not slides: slides.append(EMPTY_SLIDE.format(cat=html.escape(name.title())))
    f = SITE / cat["file"]; t = f.read_text("utf-8")
    t = re.sub(r"<!--SLIDES-->.*?<!--/SLIDES-->", lambda m: "<!--SLIDES-->\n" + "\n".join(slides) + "\n  <!--/SLIDES-->", t, flags=re.S)
    aj = json.dumps(art, ensure_ascii=False).replace("</", "<\\/")
    t = re.sub(r"/\*ART\*/.*?/\*/ART\*/", lambda m: "/*ART*/" + aj + "/*/ART*/", t, flags=re.S)
    f.write_text(t, "utf-8")

def main():
    if "--dry-run" in sys.argv:
        print("Dry-run: nu am date de probă incluse, așa că nu fac cereri și nu modific fișiere.")
        return
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Lipsește GEMINI_API_KEY. Adaugă cheia în GitHub Actions Secrets înainte de rulare.")
    ok_any, done = False, {}
    for name, cat in CFG["categories"].items():
        print(f"\n== {name}", flush=True)
        try:
            available = candidates(cat)
            print(f"  {len(available)} candidați RSS", flush=True)
            ranked = pick(cat, available)
            print(f"  Gemini a selectat {len(ranked)} candidați; descarc textele în paralel", flush=True)
            prepared = prepare_many(ranked)
            print(f"  {len(prepared)} texte disponibile; redactez într-un singur apel", flush=True)
            items = write_batch(prepared)
            for it in items: print(f"  + {it['hed'][:80]}", flush=True)
        except GeminiQuotaError as ex:
            print(f"\n! {ex}\n! Oprire fără alte apeluri Gemini.", flush=True)
            raise SystemExit(1)
        except Exception as ex:
            print(f"  ! eroare secțiune: {ex}", flush=True); items = []
        if len(items) < MIN_OK:
            print(f"  ! doar {len(items)} știri bune -> afișez mesajul de ediție indisponibilă", flush=True)
            render(name, cat, []); continue
        render(name, cat, items); ok_any = True; done[name] = items
        for it in items: HIST[it["link"]] = now.strftime("%Y-%m-%d")
    HIST_F.parent.mkdir(exist_ok=True); HIST_F.write_text(json.dumps(HIST, indent=0))
    statics.run(SITE, CFG, now.strftime("%Y-%m-%d"), done)
    if not ok_any:
        print("\nNu s-au găsit cel puțin trei știri verificate într-o secțiune; site-ul a fost actualizat cu starea ediției.", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()
