"""The published site is one static notice that the page has moved (issue #1).

Run from the repository root: python -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
NEW_HOME = "https://tools.birdhausmagic.com/upcoming-events/"
# The only elements the notice may use: nothing that loads, embeds, submits or runs.
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "main", "h1", "p", "a"}


class MovedNotice(unittest.TestCase):
    def setUp(self):
        self.html = (DOCS / "index.html").read_text(encoding="utf-8")

    def test_docs_holds_only_the_notice(self):
        files = sorted(p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*") if p.is_file())
        self.assertEqual(files, ["index.html"])

    def test_one_link_and_it_is_the_new_home(self):
        lower = self.html.lower()
        self.assertEqual(re.findall(r"""\bhref\s*=\s*["']?([^"'\s>]+)""", lower), [NEW_HOME], "any quoting or case")
        self.assertEqual(len(re.findall(r"<a\b", lower)), 1, "one link element")

    def test_no_script_redirect_or_external_asset(self):
        lower = self.html.lower()
        self.assertNotIn("<script", lower)
        self.assertNotIn("http-equiv", lower, "no meta refresh: the person follows the link themselves")
        self.assertNotRegex(lower, r"\bon[a-z]+\s*=", "no inline event handlers")
        self.assertNotRegex(lower, r'\bsrc\s*=', "no images, frames or other loaded assets")
        self.assertNotIn("<link", lower, "no stylesheets or icons from elsewhere")
        self.assertNotIn("@import", lower)
        self.assertNotIn("url(", lower)
        tags = set(re.findall(r"<([a-z][a-z0-9-]*)", lower))
        self.assertLessEqual(tags, ALLOWED_TAGS, "no object, embed, iframe, form, img or other element")

    def test_no_guest_or_event_data(self):
        lower = self.html.lower()
        for word in ("guest", "ticket", "capacity", "password", "wix"):
            self.assertNotIn(word, lower)

    def test_nothing_left_to_run(self):
        self.assertFalse((ROOT / ".github" / "workflows").exists() and any((ROOT / ".github" / "workflows").iterdir()))
        for name in ("generate.py", "data_fetcher.py", "requirements.txt", "data"):
            self.assertFalse((ROOT / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
