"""Verificări offline pentru contractul exportului, fără API sau rețea."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import export_instagram as social


ARTICLE = {
    "hed": "Știrea zilei: România pregătește un nou eveniment sportiv",
    "sum": "Organizatorii au anunțat detaliile evenimentului. Competiția reunește participanți din mai multe orașe.",
    "body": ["Organizatorii au prezentat programul competiției și condițiile de participare.",
             "Evenimentul va reuni participanți din mai multe orașe din România.",
             "Mai multe detalii vor fi comunicate de organizatori înaintea competiției."],
    "source": "Publicația de test",
}


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "2025-02-03.json"
        self.write_archive({"sport": [copy.deepcopy(ARTICLE)], "hot": [], "news": [], "music": []})

    def tearDown(self):
        self.temp.cleanup()

    def write_archive(self, data):
        self.archive.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def hashes(self, directory):
        return {str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in directory.rglob("*") if path.is_file()}

    def test_complete_export_retains_archive_date_and_romanian(self):
        out = self.root / "out"
        manifest = social.export(self.archive, out)
        self.assertEqual(manifest["edition_date"], "2025-02-03")
        self.assertEqual(manifest["article_count"], 1)
        row = manifest["articles"][0]
        self.assertNotIn("ș", row["image"])
        with Image.open(out / row["image"]) as image:
            self.assertEqual(image.size, (1080, 1350))
            self.assertEqual(image.mode, "RGB")
        caption = (out / row["caption_file"]).read_text(encoding="utf-8")
        self.assertIn(ARTICLE["hed"], caption)
        self.assertIn("Sursa: Publicația de test", caption)
        self.assertEqual(len(caption), row["caption_characters"])
        self.assertLessEqual(len(caption), 2200)
        self.assertIn("2025-02-03", (out / "README.txt").read_text(encoding="utf-8"))

    def test_rerun_is_deterministic_and_replaces_previous_export(self):
        out = self.root / "out"
        social.export(self.archive, out)
        first = self.hashes(out)
        social.export(self.archive, out)
        self.assertEqual(first, self.hashes(out))

    def test_invalid_article_preserves_previous_output(self):
        out = self.root / "out"
        social.export(self.archive, out)
        first = self.hashes(out)
        bad = copy.deepcopy(ARTICLE)
        bad["body"] = ["Un singur paragraf"]
        self.write_archive({"sport": [ARTICLE], "hot": [bad]})
        with self.assertRaisesRegex(social.ExportError, "hot, știrea 1"):
            social.export(self.archive, out)
        self.assertEqual(first, self.hashes(out))
        self.assertFalse(list(self.root.glob(".out-*")))

    def test_render_failure_preserves_previous_output(self):
        out = self.root / "out"
        social.export(self.archive, out)
        first = self.hashes(out)
        bad = copy.deepcopy(ARTICLE)
        bad["hed"] = "ImposibilDeÎncadrat" * 60
        self.write_archive({"sport": [bad]})
        with self.assertRaisesRegex(social.ExportError, "trunchiere"):
            social.export(self.archive, out)
        self.assertEqual(first, self.hashes(out))
        self.assertFalse(list(self.root.glob(".out-*")))

    def test_empty_unknown_and_overlong_captions_are_rejected(self):
        for data in ({"sport": []}, {"unknown": []}, {"sport": "știre"}):
            self.write_archive(data)
            with self.assertRaises(social.ExportError):
                social.load_articles(self.archive)
        bad = copy.deepcopy(ARTICLE)
        bad["body"] = ["Text foarte lung. " * 80] * 3
        self.write_archive({"sport": [bad]})
        with self.assertRaisesRegex(social.ExportError, "2.200"):
            social.load_articles(self.archive)

    def test_unrelated_existing_folder_is_never_replaced(self):
        out = self.root / "out"
        out.mkdir()
        (out / "personal.txt").write_text("păstrează", encoding="utf-8")
        with self.assertRaisesRegex(social.ExportError, "nu este un export"):
            social.export(self.archive, out)
        self.assertEqual((out / "personal.txt").read_text(encoding="utf-8"), "păstrează")

    def test_equal_headlines_have_distinct_stable_filenames(self):
        self.write_archive({"sport": [ARTICLE, ARTICLE]})
        _, records = social.load_articles(self.archive)
        self.assertNotEqual(records[0]["image"], records[1]["image"])
        self.assertTrue(records[0]["image"].startswith("sport/01-"))
        self.assertTrue(records[1]["image"].startswith("sport/02-"))

    def test_wrapping_preserves_words_and_bounds(self):
        draw = ImageDraw.Draw(Image.new("RGB", social.SIZE))
        font = ImageFont.truetype(str(social.find_font(None, True)), 62)
        text = "Știri importante pentru cititorii din România și din întreaga lume"
        lines = social.wrap_text(draw, text, font, 500)
        self.assertEqual(" ".join(lines), text)
        self.assertTrue(all(draw.textlength(line, font=font) <= 500 for line in lines))
        fitted, lines, step = social.fit_text(draw, text * 4, social.find_font(None, True), 936, 660, 96, 52)
        self.assertLessEqual(len(lines) * step, 660)
        self.assertGreaterEqual(fitted.size, 52)

    def test_latest_archive_uses_iso_date_and_ignores_other_json(self):
        (self.root / "2025-03-01.json").write_text("{}")
        (self.root / "notes.json").write_text("{}")
        self.assertEqual(social.latest_archive(self.root).name, "2025-03-01.json")
        with self.assertRaises(social.ExportError):
            social.archive_date(self.root / "2025-02-30.json")


if __name__ == "__main__":
    unittest.main()
