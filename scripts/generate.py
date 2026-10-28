#!/usr/bin/env python3
"""ACQ: RSS -> selecție și rezumare în română cu Gemini -> actualizează paginile HTML.
Rulare:  GEMINI_API_KEY=... python scripts/generate.py (opțiunea --dry-run nu schimbă fișierele)"""
import os, re, sys, json, time, html, calendar, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent))
import statics

ROOT = Path(__file__).parent
SITE = Path(os.getenv("SITE_DIR", ROOT.parent))
CFG = json.loads((ROOT / "feeds.json").read_text("utf-8"))
MODEL = os.getenv("GEMINI_MODEL", CFG["model"])
N, MIN_OK, MAX_AGE_H = 5, 3, 40
UA = {"User-Agent": "Mozilla/5.0 (compatible; ACQMediaBot/1.0)"}
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

def gemini(prompt, schema):
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "responseSchema": schema}}
    for a in range(5):
        r = requests.post(url, json=body, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=120)
        if r.status_code in (429, 500, 503):
            time.sleep(20 * (a + 1)); continue
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
    out, seen, cut = [], set(), time.time() - MAX_AGE_H * 3600
    for url in cat["feeds"]:
        try:
            d = feedparser.parse(requests.get(url, headers=UA, timeout=20).content)
        except Exception as ex:
            print(f"  ! feed indisponibil {url}: {ex}"); continue
        n = 0
        for e in d.entries[:15]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t and calendar.timegm(t) < cut: continue
            link, title = e.get("link"), re.sub(r"\s+", " ", e.get("title", "")).strip()
            key = re.sub(r"\W+", "", title.lower())[:60]
            if not link or not title or key in seen or link in HIST: continue
            seen.add(key); n += 1
            out.append({"title": title, "link": link, "rss_img": rss_img(e),
                        "source": (d.feed.get("title", "") or url.split("/")[2]).split(" - ")[0].split(" | ")[0].strip(),
                        "snippet": re.sub(r"<[^>]+>", "", html.unescape(e.get("summary", "")))[:600]})
        print(f"  {n:2d} articole noi  <- {url}")
    return out

def pick(cat, cands):
    cands = cands[:45]
    lst = "\n".join(f"{i}. [{c['source']}] {c['title']} — {c['snippet'][:160]}" for i, c in enumerate(cands))
    r = gemini(f"Ești redactor-șef la un site de știri minimalist în limba română. Secțiunea: {cat['brief']}\n"
               f"Din lista de mai jos alege cele {N+3} cele mai importante și mai diverse știri (fără două despre același eveniment), "
               f"în ordinea importanței. Returnează doar indicii.\n\n{lst}",
               {"type": "OBJECT", "properties": {"ids": {"type": "ARRAY", "items": {"type": "INTEGER"}}}, "required": ["ids"]})
    return [cands[i] for i in dict.fromkeys(r["ids"]) if isinstance(i, int) and 0 <= i < len(cands)]

def write(c):
    import requests, trafilatura
    page = requests.get(c["link"], headers=UA, timeout=25).text
    text = trafilatura.extract(page, include_comments=False) or ""
    m = trafilatura.extract_metadata(page)
    c["img"] = (m.image if m and m.image else None) or c.get("rss_img")
    text = text[:7000] if len(text) > 600 else c["snippet"]
    if len(text) < 200: return None
    r = gemini(
        f"Ești redactor la un site de știri în limba română. Pe baza EXCLUSIV a textului sursă de mai jos, scrie o știre originală în română, "
        f"cu cuvintele tale (nu copia fraze din sursă, nu traduce cuvânt cu cuvânt). Nu adăuga nume, cifre, date sau citate care nu apar în text. "
        f"Acuzațiile, zvonurile și declarațiile controversate se atribuie explicit ({c['source']} / persoana citată). Ton neutru, informativ. "
        f"Dacă textul nu conține suficiente informații pentru o știre, pune skip=true.\n"
        f"Câmpuri: cat = eticheta secțiunii (1-3 cuvinte, ex. Tenis, Geopolitică); hed = titlu până în 110 caractere; "
        f"sum = rezumat de 2-3 propoziții (35-55 cuvinte); body = 3-4 paragrafe de câte 2-4 propoziții.\n\n"
        f"SURSA: {c['source']}\nTITLU ORIGINAL: {c['title']}\nTEXT:\n{text}",
        {"type": "OBJECT", "properties": {"skip": {"type": "BOOLEAN"}, "cat": {"type": "STRING"}, "hed": {"type": "STRING"},
         "sum": {"type": "STRING"}, "body": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["skip"]})
    if r.get("skip") or not (r.get("hed") and r.get("sum") and r.get("body")): return None
    return {**r, "source": c["source"], "link": c["link"], "img": c["img"]}

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
        print(f"\n== {name}")
        try:
            items = []
            for c in pick(cat, candidates(cat)):
                if len(items) == N: break
                try:
                    it = write(c)
                except Exception as ex:
                    print(f"  ! sar peste {c['link']}: {ex}"); continue
                if it: items.append(it); print(f"  + {it['hed'][:80]}")
        except Exception as ex:
            print(f"  ! eroare secțiune: {ex}"); items = []
        if len(items) < MIN_OK:
            print(f"  ! doar {len(items)} știri bune -> afișez mesajul de ediție indisponibilă")
            render(name, cat, []); continue
        render(name, cat, items); ok_any = True; done[name] = items
        for it in items: HIST[it["link"]] = now.strftime("%Y-%m-%d")
    HIST_F.parent.mkdir(exist_ok=True); HIST_F.write_text(json.dumps(HIST, indent=0))
    statics.run(SITE, CFG, now.strftime("%Y-%m-%d"), done)
    if not ok_any:
        print("\nNu s-au găsit cel puțin trei știri verificate într-o secțiune; site-ul a fost actualizat cu starea ediției.")
    sys.exit(0)

if __name__ == "__main__":
    main()
