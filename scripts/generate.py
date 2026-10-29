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
N, MIN_OK, MAX_AGE_H = 2, 2, 40
UA = {"User-Agent": "Mozilla/5.0 (compatible; ACQMediaBot/1.0)"}
FEED_TIMEOUT, ARTICLE_TIMEOUT, GEMINI_TIMEOUT = (5, 12), (5, 15), 75
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
            "generationConfig": {"maxOutputTokens": 2048, "responseMimeType": "application/json", "responseSchema": schema}}
    try:
        response = requests.post(
            url,
            json=body,
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
            timeout=GEMINI_TIMEOUT,
        )
    except requests.RequestException as ex:
        raise RuntimeError(f"Gemini nu a răspuns; cererea nu a fost retrimisă: {ex}") from ex

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

def shortlist(items, limit=2):
    """Păstrează surse diverse fără un apel Gemini separat de selecție."""
    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)
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
        text = trafilatura.extract(page, include_comments=False) or ""
        meta = trafilatura.extract_metadata(page)
        img = (meta.image if meta and meta.image else None) or img
    except Exception as ex:
        print(f"  ! articol indisponibil {c['link']}: {ex}", flush=True)
    if len(text) < 600: text = c["snippet"]
    if len(text) < 200: return None
    return {**c, "img": img, "article_text": text[:1600]}

def prepare_many(items):
    if not items: return []
    with ThreadPoolExecutor(max_workers=min(12, len(items))) as pool:
        prepared = list(pool.map(prepare, items))
    return [item for item in prepared if item]

def write_batch(items):
    if not items: return []
    entries = []
    for i, c in enumerate(items):
        entries.append(f"ID: {i}\nSECȚIUNE: {c['_section']} — {c['_brief']}\nSURSĂ: {c['source']}\nTITLU ORIGINAL: {c['title']}\nTEXT: {c['article_text']}")
    schema = {"type": "OBJECT", "properties": {"articles": {"type": "ARRAY", "items": {
        "type": "OBJECT", "properties": {"id": {"type": "INTEGER"}, "skip": {"type": "BOOLEAN"},
        "cat": {"type": "STRING"}, "hed": {"type": "STRING"}, "sum": {"type": "STRING"},
        "body": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["id", "skip"]}}},
        "required": ["articles"]}
    prompt = (
        "Ești redactor la un site de știri în limba română. Primești texte numerotate din mai multe secțiuni. "
        "Alege cel mult 2 știri distincte, importante și susținute clar pentru fiecare secțiune. Nu amesteca secțiunile și nu combina articole. "
        "Returnează articolele în ordinea importanței din fiecare secțiune. Pentru fiecare ID întoarce un obiect cu acel id și skip. "
        "Pentru o știre publicabilă, skip=false și completează toate câmpurile; pentru una insuficient documentată, skip=true. "
        "Scrie original, cu propriile cuvinte; nu copia și nu traduce fraze. Folosește EXCLUSIV faptele din text. Nu inventa nume, cifre, date sau citate. "
        "Atribuie explicit sursei acuzațiile și declarațiile controversate. Ton neutru. "
        "Câmpuri pentru știrile publicabile: cat = etichetă de 1-3 cuvinte; hed = titlu de maximum 95 de caractere; "
        "sum = rezumat de 1-2 propoziții, 20-32 de cuvinte; body = exact 2 paragrafe scurte, fiecare de 1-2 propoziții. "
        "Păstrează ID-ul fiecărui text și nu combina informații din articole diferite.\n\n" + "\n\n---\n\n".join(entries)
    )
    result = gemini(prompt, schema)
    by_id = {}
    for article in result.get("articles", []):
        i = article.get("id")
        if not isinstance(i, int) or i < 0 or i >= len(items) or article.get("skip"):
            continue
        if not (article.get("hed") and article.get("sum") and article.get("body")):
            continue
        c = items[i]
        by_id[i] = {**article, "source": c["source"], "link": c["link"], "img": c["img"], "_section": c["_section"]}
    return [by_id[i] for i in range(len(items)) if i in by_id]

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
    ok_any, done, all_candidates = False, {}, []
    for name, cat in CFG["categories"].items():
        print(f"\n== {name}", flush=True)
        try:
            available = candidates(cat)
            selected = shortlist(available, 2)
            print(f"  {len(available)} candidați RSS; descarc maximum {len(selected)} articole", flush=True)
            for item in selected:
                all_candidates.append({**item, "_section": name, "_brief": cat["brief"]})
        except Exception as ex:
            print(f"  ! eroare la colectarea știrilor: {ex}", flush=True)
    prepared = prepare_many(all_candidates)
    print(f"\n{len(prepared)} texte disponibile; redactez maximum 8 texte într-un singur apel Gemini", flush=True)
    try:
        generated = write_batch(prepared)
        print(f"Gemini: {1 if prepared else 0} cereri pentru toate secțiunile", flush=True)
    except GeminiQuotaError as ex:
        print(f"\n! {ex}\n! Oprire fără alte apeluri Gemini.", flush=True)
        raise SystemExit(1)
    except Exception as ex:
        raise SystemExit(f"Eroare la redactarea cu Gemini. Workflow-ul se oprește fără reîncercări: {ex}") from ex
    for name, cat in CFG["categories"].items():
        items = [item for item in generated if item["_section"] == name][:N]
        for item in items:
            item.pop("_section", None)
        if len(items) < MIN_OK:
            print(f"  ! {name}: doar {len(items)} știri bune -> afișez mesajul de ediție indisponibilă", flush=True)
            render(name, cat, []); continue
        for it in items: print(f"  + {it['hed'][:80]}", flush=True)
        render(name, cat, items); ok_any = True; done[name] = items
        for it in items: HIST[it["link"]] = now.strftime("%Y-%m-%d")
    HIST_F.parent.mkdir(exist_ok=True); HIST_F.write_text(json.dumps(HIST, indent=0))
    statics.run(SITE, CFG, now.strftime("%Y-%m-%d"), done)
    if not ok_any:
        print("\nNu s-au găsit suficiente știri verificate într-o secțiune; site-ul a fost actualizat cu starea ediției.", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()
