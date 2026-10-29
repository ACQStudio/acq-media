"""Pagini statice generate zilnic: arhivă (calendar + pagini pe zile), index, SEO/GEO, sitemap, robots, llms.txt."""
import json, re, html, os
from pathlib import Path
e = html.escape
ORDER = ["sport", "hot", "news", "music"]
BRAND = "ACQ Media"
NAME = {"sport": "Sport", "hot": "Hot", "news": "News", "music": "Music"}
COL = {"sport": "#22c55e", "hot": "#ef4444", "news": "#e8e8ed", "music": "#3b82f6"}
TITLE = {"sport": "Știri sportive de azi", "hot": "Cancan și showbiz de azi",
         "news": "Geopolitică și economie, știrile de azi", "music": "Muzică și entertainment, știrile de azi"}
DESC = {"sport": "Cele mai importante știri sportive ale zilei: fotbal, tenis, Formula 1 și rezultate majore, pe scurt, cu sursa originală.",
        "hot": "Știri din showbiz: scandaluri, nunți, divorțuri și vedete din România și din lume, cu sursa originală.",
        "news": "Știri de geopolitică, economie, bănci și afaceri, pe scurt, cu sursa originală.",
        "music": "Știri din muzică și entertainment: lansări, turnee, concerte și festivaluri, cu sursa originală."}
LUNI = "ianuarie februarie martie aprilie mai iunie iulie august septembrie octombrie noiembrie decembrie".split()
def ro(iso): y, m, d = map(int, iso.split("-")); return f"{d} {LUNI[m-1]} {y}"

def sub(path, a, b, body):
    t = path.read_text("utf-8")
    t, n = re.subn(re.escape(a) + ".*?" + re.escape(b), lambda m: a + body + b, t, flags=re.S)
    assert n == 1, (path.name, a)
    path.write_text(t, "utf-8")

def site_base(cfg):
    configured = cfg.get("site_url", "").strip().rstrip("/")
    if configured: return configured
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if "/" not in repo: return ""
    owner, name = repo.split("/", 1)
    if name.lower() == f"{owner}.github.io".lower(): return f"https://{owner}.github.io"
    return f"https://{owner}.github.io/{name}"

def head(url, title, desc, ld):
    j = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    canonical = f'<link rel="canonical" href="{e(url)}">\n' if url else ""
    og_url = f'<meta property="og:url" content="{e(url)}">' if url else ""
    return (f'\n<title>{e(title)}</title>\n<meta name="description" content="{e(desc)}">\n{canonical}'
            f'<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">'
            f'{og_url}<meta property="og:locale" content="ro_RO"><meta property="og:site_name" content="{BRAND}">\n'
            f'<meta name="twitter:card" content="summary"><meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">\n'
            f'<script type="application/ld+json">{j}</script>\n')

def items_ld(entries, iso):
    return {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": {
        "@type": "NewsArticle", "headline": it["hed"], "description": it["sum"], "datePublished": iso, "inLanguage": "ro",
        "isBasedOn": it["link"], "publisher": {"@type": "Organization", "name": BRAND}}} for i, it in enumerate(entries)]}

def page_ld(base, url, title, desc, entries, iso):
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "description": desc, "inLanguage": "ro",
          "mainEntity": items_ld(entries, iso)}
    if url: ld["url"] = url
    if base: ld["isPartOf"] = {"@type": "WebSite", "name": BRAND, "url": base + "/"}
    return ld

DAY = open(Path(__file__).parent / "day_template.html", encoding="utf-8").read()

def day_page(base, iso, data):
    cats = [c for c in ORDER if data.get(c)]
    body = "".join(f'<section data-c="{c}" style="--c:{COL[c]}"><h2><i></i>{NAME[c]}</h2>' + "".join(
        f'<article><h3>{e(it["hed"])}</h3><p>{e(it["sum"])}</p><details><summary>Citește mai mult</summary>'
        + "".join(f"<p>{e(p)}</p>" for p in it["body"]) +
        f'</details><p class="src">Sursa: <a href="{e(it["link"])}" rel="noopener" target="_blank">{e(it["source"])}</a></p></article>' for it in data[c]) + "</section>" for c in cats)
    chips = "".join(f'<button aria-pressed="true" data-c="{c}" style="--c:{COL[c]}">{NAME[c]}</button>' for c in cats)
    allitems = [it for c in cats for it in data[c]]
    title, desc = f"Știrile din {ro(iso)} | {BRAND}", f"Cele mai importante știri din {ro(iso)} la Sport, Hot, News și Music."
    day_url = f"{base}/arhiva/{iso}.html" if base else ""
    return (DAY.replace("@@HEAD@@", head(day_url, title, desc, page_ld(base, day_url, title, desc, allitems, iso)))
               .replace("@@DATE@@", ro(iso)).replace("@@CHIPS@@", chips).replace("@@BODY@@", body))

def run(site, cfg, iso, today):
    base = site_base(cfg)
    ad = Path(__file__).parent / "data" / "archive"; ad.mkdir(parents=True, exist_ok=True)
    if today: (ad / f"{iso}.json").write_text(json.dumps(today, ensure_ascii=False), "utf-8")
    days = {f.stem: json.loads(f.read_text("utf-8")) for f in sorted(ad.glob("*.json"))}
    (site / "arhiva").mkdir(exist_ok=True)
    for d, data in days.items(): (site / "arhiva" / f"{d}.html").write_text(day_page(base, d, data), "utf-8")
    last = max(days) if days else iso
    for c in ORDER:   # SEO pe paginile de secțiune
        t = f"{BRAND} {NAME[c]} — {TITLE[c]}"; u = f"{base}/{c}.html" if base else ""
        sub(site / f"{c}.html", "<!--SEO-->", "<!--/SEO-->", head(u, t, DESC[c], page_ld(base, u, t, DESC[c], today.get(c, []), iso)))
    cards = ""   # folderele din index; doar ediția de azi, fără titluri vechi prezentate ca noi
    for c in ORDER:
        its = today.get(c, [])
        count = len(its)
        count_text = "știre" if count == 1 else "știri"
        hs = "".join(f'<span class="h">{e(x["hed"])}</span>' for x in its[:2]) or '<span class="h">Ediția de azi nu este încă disponibilă.</span>'
        state = "empty" if not its else "ready"
        empty = "true" if not its else "false"
        card_class = "f no-news" if not its else "f"
        cards += (f'<a class="{card_class}" data-c="{c}" data-empty="{empty}" data-state="{state}" href="{c}.html" style="--c:{COL[c]}"><span class="tab"></span><span class="bk"></span>'
                  f'<span class="fr"><b class="n">{NAME[c]}</b><span class="k">{count} {count_text} azi</span>{hs}</span></a>\n')
    ix = site / "index.html"; sub(ix, "<!--CARDS-->", "<!--/CARDS-->", "\n" + cards)
    t, d = f"{BRAND} — Știrile zilei, pe scurt", "Cele mai importante știri de azi, în Sport, Hot, News și Music. Pe scurt, cu sursa originală."
    home_url = base + "/" if base else ""
    home_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": BRAND, "inLanguage": "ro", "description": d}
    if home_url:
        home_ld["url"] = home_url
        home_ld["publisher"] = {"@type": "Organization", "name": BRAND, "url": home_url}
    sub(ix, "<!--SEO-->", "<!--/SEO-->", head(home_url, t, d, home_ld))
    ar = site / "arhiva.html"; u = base + "/arhiva.html" if base else ""; t2 = f"Arhiva știrilor | {BRAND}"
    d2 = "Alege o zi din calendar și vezi știrile publicate atunci: Sport, Hot, News și Music."
    archive_ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": t2, "inLanguage": "ro", "description": d2}
    if u: archive_ld["url"] = u
    sub(ar, "<!--SEO-->", "<!--/SEO-->", head(u, t2, d2, archive_ld))
    sub(ar, "/*DATES*/", "/*/DATES*/", json.dumps({d: [c for c in ORDER if days[d].get(c)] for d in days}))
    sub(ar, "<!--LINKS-->", "<!--/LINKS-->", "".join(f'<li><a href="arhiva/{d}.html">{ro(d)}</a></li>' for d in sorted(days, reverse=True)))
    urls = ([(base + "/", last)] + [(f"{base}/{p}.html", last) for p in ORDER + ["arhiva"]] + [(f"{base}/arhiva/{d}.html", d) for d in sorted(days)]) if base else []
    (site / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"<url><loc>{e(u)}</loc><lastmod>{m}</lastmod></url>\n" for u, m in urls) + "</urlset>\n", "utf-8")
    bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended", "Applebot-Extended"]
    sitemap_line = f"Sitemap: {base}/sitemap.xml\n" if base else ""
    (site / "robots.txt").write_text("User-agent: *\nAllow: /\n\n" + "".join(f"User-agent: {b}\nAllow: /\n\n" for b in bots) + sitemap_line, "utf-8")
    (site / "llms.txt").write_text(f"""# {BRAND}
> Site românesc de știri zilnice, minimalist: până la două știri pe zi în fiecare secțiune, rezumate în română din publicații românești și internaționale. Fiecare știre are link către articolul original.

## Secțiuni
""" + "".join(f"- [{NAME[c]}]({base}/{c}.html): {DESC[c]}\n" for c in ORDER) + f"""
## Arhivă
- [Calendar]({base}/arhiva.html): alegi o zi și vezi știrile de atunci; fiecare zi are propria pagină ({base}/arhiva/AAAA-LL-ZZ.html).

## Despre conținut
Fiecare știre este un rezumat rescris în română al unui articol publicat de o altă publicație; sursa este numită și legată în pagină. Pentru detalii complete, citează sau consultă articolul original.
""", "utf-8")
