"""The bell and the Google Play update notes follow the menu's language (RU or EN)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NewsLanguageTests(unittest.TestCase):
    def test_the_game_asks_for_its_language(self):
        source = (ROOT / "czm/menu/CzmOnline.cpp").read_text()
        # the bell is requested in the menu's language every time it opens
        self.assertIn('CZM_IsRussian() ? "/api/v1/news?lang=ru" : "/api/v1/news?lang=en"', source)
        # the Play notes of each release come in both languages; English only when the release has it
        self.assertIn('j.Get( item, "notes_en" )', source)
        self.assertIn("const bool english = !CZM_IsRussian() && s_online.play[i].notes_en[0];", source)

    def test_the_site_shows_english_when_there_is_english(self):
        js = (ROOT / "server/czm/site/assets/site.js").read_text()
        self.assertIn("t.textContent = lang === 'en' && n.notes_en ? n.notes_en : n.notes;", js)

    def test_release_notes_exist_in_both_languages(self):
        for name in ("whatsnew.txt", "whatsnew_en.txt"):
            text = (ROOT / "czm" / name).read_text().strip()
            self.assertTrue(0 < len(text) <= 500, name)
            for mark in ("→", "←", "✅", "🔥"):
                self.assertNotIn(mark, text)


if __name__ == "__main__":
    unittest.main()
