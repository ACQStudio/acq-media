#!/usr/bin/env python3
"""Exportă ediția ACQ în imagini și descrieri Instagram, fără apeluri AI."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import tempfile
import unicodedata
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
SIZE = (1080, 1350)
GENERATOR = "acq-instagram"
SECTIONS = {
    "sport": {"name": "Sport", "color": "#307c53", "hashtags": ["#ACQMedia", "#ACQSport", "#Sport", "#SportRomanesc"]},
    "hot": {"name": "Hot", "color": "#b44948", "hashtags": ["#ACQMedia", "#ACQHot", "#Showbiz", "#Monden"]},
    "news": {"name": "News", "color": "#5e6670", "hashtags": ["#ACQMedia", "#ACQNews", "#Stiri", "#Romania"]},
    "music": {"name": "Music", "color": "#4b6a9c", "hashtags": ["#ACQMedia", "#ACQMusic", "#Muzica", "#IndustriaMuzicala"]},
}
TOPIC_TAGS = {
    "sport": [("fotbal", "#Fotbal"), ("tenis", "#Tenis"), ("formula 1", "#Formula1"),
              ("box", "#Box"), ("baschet", "#Baschet"), ("rugby", "#Rugby"),
              ("olimp", "#JocurileOlimpice"), ("campion", "#Campionat")],
    "hot": [("asia express", "#AsiaExpress"), ("divort", "#Vedete"), ("cantaret", "#Vedete"),
            ("actor", "#Vedete"), ("influencer", "#Influenceri"), ("nunta", "#NuntaVedetelor"),
            ("relatie", "#ShowbizRomanesc"), ("vedeta", "#VedeteRomania")],
    "news": [("politic", "#Politica"), ("geopolit", "#Geopolitica"), ("aleger", "#Alegeri"),
             ("economie", "#Economie"), ("economic", "#Economie"), ("afaceri", "#Afaceri"),
             ("energie", "#Energie"), ("razboi", "#Actualitate"), ("ucrain", "#Ucraina")],
    "music": [("concert", "#Concerte"), ("festival", "#Festivaluri"), ("album", "#AlbumNou"),
              ("turneu", "#Turneu"), ("muzic", "#StiriMuzicale"), ("grammy", "#Grammy"),
              ("spotify", "#Spotify"), ("artist", "#Artist")],
}


class ExportError(ValueError):
    """O eroare explicabilă, fără înlocuirea exportului anterior."""


def clean_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExportError(f"Câmpul {field} trebuie să conțină text.")
    value = " ".join(value.split())
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ExportError(f"Câmpul {field} conține caractere de control.")
    return value


def archive_date(path: Path) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
        raise ExportError("Arhiva trebuie să aibă numele AAAA-LL-ZZ.json.")
    try:
        dt.date.fromisoformat(path.stem)
    except ValueError as error:
        raise ExportError(f"Data arhivei nu este validă: {path.stem}.") from error
    return path.stem


def latest_archive(directory: Path = ROOT / "data" / "archive") -> Path:
    candidates = sorted(path for path in directory.glob("*.json")
                        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem))
    if not candidates:
        raise ExportError(f"Nu există nicio ediție în {directory}.")
    return candidates[-1]


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:72].rstrip("-") or "stire"


def hashtags_for(section: str, article: dict) -> str:
    searchable = article["hed"] + " " + article["sum"] + " " + " ".join(article["body"])
    folded = unicodedata.normalize("NFKD", searchable).encode("ascii", "ignore").decode("ascii").lower()
    tags = list(SECTIONS[section]["hashtags"])
    for phrase, tag in TOPIC_TAGS[section]:
        if phrase in folded and tag not in tags:
            tags.append(tag)
        if len(tags) >= 5:
            break
    return " ".join(tags[:5])


def caption_for(section: str, article: dict) -> str:
    caption = (article["hed"] + "\n\n" + "\n\n".join(article["body"])
               + "\n\n" + hashtags_for(section, article))
    if len(caption) > 2200:
        raise ExportError(f"Descrierea pentru «{article['hed']}» are {len(caption)} caractere; limita exportului este 2.200. Textul nu a fost trunchiat.")
    return caption


def load_articles(path: Path) -> tuple[str, list[dict]]:
    edition = archive_date(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ExportError(f"Nu pot citi arhiva {path.name}: {error}") from error
    if not isinstance(data, dict) or set(data) - SECTIONS.keys():
        raise ExportError("Arhiva trebuie să conțină secțiunile sport, hot, news și/sau music.")
    records = []
    for section in SECTIONS:
        entries = data.get(section, [])
        if not isinstance(entries, list):
            raise ExportError(f"Secțiunea {section} trebuie să fie o listă de știri.")
        for index, item in enumerate(entries, 1):
            context = f"{section}, știrea {index}"
            if not isinstance(item, dict):
                raise ExportError(f"{context}: știrea trebuie să fie un obiect.")
            if item.get("skip") is True:
                continue
            article = {field: clean_text(item.get(field), f"{context} / {field}")
                       for field in ("hed", "sum", "source")}
            article["img"] = item.get("img") if isinstance(item.get("img"), str) else ""
            body = item.get("body")
            if not isinstance(body, list) or not 3 <= len(body) <= 4:
                raise ExportError(f"{context}: body trebuie să conțină 3 sau 4 paragrafe.")
            article["body"] = [clean_text(paragraph, f"{context} / body") for paragraph in body]
            caption = caption_for(section, article)
            base = f"{index:02d}-{slugify(article['hed'])}"
            records.append({"section": section, "index": index, "article": article,
                            "caption": caption, "image": f"{section}/{base}.png",
                            "caption_file": f"{section}/{base}.txt"})
    if not records:
        raise ExportError("Ediția nu conține știri complete de exportat.")
    return edition, records


def find_font(explicit: Path | None, bold: bool) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise ExportError(f"Fontul nu există: {explicit}")
        return explicit
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    mac_name = "Arial Bold.ttf" if bold else "Arial.ttf"
    choices = [Path("/usr/share/fonts/truetype/dejavu") / filename,
               Path("/usr/share/fonts/dejavu-sans-fonts") / filename,
               Path("/System/Library/Fonts/Supplemental") / mac_name,
               Path("/Library/Fonts") / mac_name]
    found = next((path for path in choices if path.is_file()), None)
    if found is None:
        raise ExportError("Nu găsesc fonturi DejaVu Sans sau Arial. Instalează fonts-dejavu-core ori folosește --font-regular și --font-bold.")
    return found


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
              max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if draw.textlength(word, font=font) > max_width:
            raise ExportError(f"Un cuvânt este prea lung pentru imagine: {word[:60]}")
        candidate = f"{current} {word}" if current else word
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_text(draw: ImageDraw.ImageDraw, text: str, font_path: Path, max_width: int,
             max_height: int, largest: int, smallest: int, leading: float = 1.13):
    for size in range(largest, smallest - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        try:
            lines = wrap_text(draw, text, font, max_width)
        except ExportError:
            continue
        step = round(size * leading)
        if len(lines) * step <= max_height:
            return font, lines, step
    raise ExportError(f"Textul nu încape în imagine la dimensiunea minimă de {smallest}px: «{text[:100]}». Exportul s-a oprit fără trunchiere.")


def draw_lines(draw, xy, lines, font, step, fill):
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill, anchor="lt")
        y += step


def source_photo(url: str) -> Image.Image | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ACQMediaPost/1.0)"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if not response.headers.get_content_type().startswith("image/"):
                return None
            data = response.read(12 * 1024 * 1024 + 1)
        if len(data) > 12 * 1024 * 1024:
            return None
        photo = Image.open(BytesIO(data))
        photo.verify()
        photo = Image.open(BytesIO(data))
        return ImageOps.exif_transpose(photo).convert("RGB")
    except (OSError, ValueError, urllib.error.URLError):
        return None


def render_poster(section: str, article: dict, edition: str, output: Path,
                  regular: Path, bold: Path) -> None:
    image = Image.new("RGB", SIZE, "#f5f3ee")
    draw = ImageDraw.Draw(image)
    ink, muted = "#161719", "#6d6c68"
    section_data = SECTIONS[section]
    brand_font = ImageFont.truetype(str(bold), 32)
    small_font = ImageFont.truetype(str(regular), 23)
    draw.text((72, 73), f"ACQ {section_data['name']}", fill=ink, font=brand_font, anchor="lt")
    date_label = dt.date.fromisoformat(edition).strftime("%d.%m.%Y")
    draw.text((1008, 79), date_label, fill=muted, font=small_font, anchor="rt")
    draw.line((72, 145, 1008, 145), fill=section_data["color"], width=3)
    photo = source_photo(article.get("img", ""))
    if photo is not None:
        photo = ImageOps.fit(photo, (936, 490), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        image.paste(photo, (72, 190))
    else:
        draw.rounded_rectangle((72, 190, 1008, 680), radius=22, fill=section_data["color"])
        label_font = ImageFont.truetype(str(bold), 48)
        draw.text((120, 385), f"ACQ {section_data['name'].upper()}", fill="#f5f3ee", font=label_font, anchor="lm")
    font, lines, step = fit_text(draw, article["hed"], bold, 936, 392, 76, 45, 1.12)
    draw_lines(draw, (72, 730), lines, font, step, ink)
    draw.line((72, 1211, 1008, 1211), fill="#d7d5cf", width=1)
    draw.text((72, 1295), "media.acq.ro", fill=muted, font=ImageFont.truetype(str(regular), 20), anchor="lt")
    image.save(output, format="PNG", optimize=True)


def validate_output(output: Path) -> None:
    if output.is_symlink():
        raise ExportError("Folderul de export nu poate fi un link simbolic.")
    if output.exists():
        if not output.is_dir():
            raise ExportError(f"Calea de export există și nu este un folder: {output}")
        try:
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ExportError("Folderul există deja și nu este un export ACQ. Alege un folder gol nou.") from error
        if not isinstance(manifest, dict) or manifest.get("generator") != GENERATOR or manifest.get("version") != 1:
            raise ExportError("Folderul existent nu este un export ACQ recunoscut; nu îl înlocuiesc.")


def export(archive: Path, output: Path, font_regular: Path | None = None,
           font_bold: Path | None = None) -> dict:
    edition, records = load_articles(archive)
    regular, bold = find_font(font_regular, False), find_font(font_bold, True)
    output = output.absolute()
    validate_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-new-", dir=output.parent))
    backup = None
    committed = False
    try:
        manifest = {"generator": GENERATOR, "version": 1, "edition_date": edition,
                    "image_size": list(SIZE), "article_count": len(records), "articles": []}
        for record in records:
            article = record["article"]
            target = stage / record["image"]
            target.parent.mkdir(exist_ok=True)
            try:
                render_poster(record["section"], article, edition, target, regular, bold)
            except (OSError, ValueError) as error:
                raise ExportError(f"Nu am putut exporta {record['section']}, știrea {record['index']}: {error}") from error
            (stage / record["caption_file"]).write_text(record["caption"], encoding="utf-8")
            manifest["articles"].append({"section": record["section"], "index": record["index"],
                "headline": article["hed"], "source": article["source"], "image": record["image"],
                "caption_file": record["caption_file"], "caption_characters": len(record["caption"])})
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        readme = (f"ACQ Media — pachet Instagram\nEdiția: {edition}\nȘtiri: {len(records)}\n\n"
                  "Fiecare știre are o imagine PNG de 1080 × 1350 și un fișier TXT cu descrierea în română.\n"
                  "1. Verifică știrea și data ediției înainte de publicare.\n"
                  "2. Încarcă imaginea în Instagram.\n"
                  "3. Copiază descrierea din fișierul TXT cu același nume și publică manual.\n\n"
                  "Fiecare imagine folosește fotografia articolului, dacă este disponibilă, cu un design ACQ și titlul știrii.\n"
                  "Descrierile includ textul știrii și hashtaguri tematice. Exportul nu apelează AI și nu publică în contul Instagram.\n"
                  "Data este cea a arhivei, chiar dacă pachetul este refăcut într-o altă zi.\n")
        (stage / "README.txt").write_text(readme, encoding="utf-8")
        if output.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{output.name}-old-", dir=output.parent))
            backup.rmdir()
            output.replace(backup)
        try:
            stage.replace(output)
        except OSError:
            if backup is not None:
                try:
                    backup.replace(output)
                    backup = None
                except OSError as error:
                    raise ExportError(f"Nu am putut restaura folderul inițial; fișierele lui sunt păstrate în {backup}.") from error
            raise
        committed = True
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if committed and backup is not None and backup.exists():
            shutil.rmtree(backup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Arhivă AAAA-LL-ZZ.json; implicit, cea mai recentă ediție salvată.")
    parser.add_argument("--output", type=Path, required=True, help="Folder nou sau un export ACQ anterior, înlocuit numai după validare.")
    parser.add_argument("--font-regular", type=Path)
    parser.add_argument("--font-bold", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = export(args.archive or latest_archive(), args.output, args.font_regular, args.font_bold)
    except (ExportError, OSError) as error:
        parser.exit(1, f"Export Instagram oprit: {error}\n")
    print(f"Instagram: {manifest['article_count']} imagini și descrieri pentru ediția {manifest['edition_date']}, în {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
