"""Tests for the market CV analyser. stdlib unittest, runs anywhere:

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cvcorpus import (  # noqa: E402
    build_playbooks, check_cv, contrast, detect_language, fold, load_corpus, load_seeds, sections, terms,
)
from synthetic import write_corpus  # noqa: E402

SEEDS = load_seeds(ROOT / "seed_playbooks.json")


class TextTests(unittest.TestCase):
    def test_fold_strips_accents(self):
        self.assertEqual(fold("Comptabilité de A à Z"), "comptabilite de a a z")

    def test_language(self):
        self.assertEqual(detect_language("Je suis comptable dans une fiduciaire et je fais la TVA pour les clients."), "fr")
        self.assertEqual(detect_language("Ik ben boekhouder in een boekhoudkantoor en ik doe de btw voor de klanten."), "nl")
        self.assertEqual(detect_language("I am an accountant at a firm and I file the VAT returns for the clients."), "en")

    def test_sections_are_multilingual_and_ordered(self):
        cv = "PROFIL\n...\nEXPÉRIENCE PROFESSIONNELLE\n...\nFORMATION\n...\nLangues :\n..."
        self.assertEqual(sections(cv), ["profile", "experience", "education", "languages"])

    def test_terms_skip_stopword_edges_and_dates(self):
        t = terms("Stagiaire ITAA depuis 12/03/2021 et comptabilité de A à Z")
        self.assertIn("stagiaire itaa", t)
        self.assertNotIn("12/03/2021", t)
        self.assertFalse(any(x.startswith("et ") or x.endswith(" de") for x in t))


class StatsTests(unittest.TestCase):
    def test_shrinkage_tempers_small_groups(self):
        # 3 of 3 is not "100% vs 0%": with shrinkage the evidence is weak
        _, _, z_small = contrast(3, 3, 0, 3)
        _, _, z_big = contrast(30, 30, 0, 30)
        self.assertLess(z_small, z_big)
        self.assertLess(z_small, 3.0)


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.docs = load_corpus(write_corpus(Path(cls.tmp.name) / "corpus"))
        cls.books = build_playbooks(cls.docs, SEEDS)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def conv(self, key, market="BE", position="accounting"):
        return next(c for c in self.books[(market, position)]["conventions"] if c["key"] == key)

    def test_groups_and_languages(self):
        be = self.books[("BE", "accounting")]
        self.assertEqual(be["cvs"], 40)
        self.assertEqual(set(be["cv_languages"]), {"fr", "nl"})

    def test_planted_belgian_conventions_are_found_and_are_belgian(self):
        for key in ("itaa", "full_cycle", "fiduciaire"):
            c = self.conv(key)
            self.assertGreater(c["share"], 0.4, key)
            self.assertEqual(c["elsewhere"], 0.0, key)

    def test_french_market_uses_cabinet_not_fiduciaire(self):
        self.assertGreater(self.conv("cabinet", "FR")["share"], 0.4)
        fr_terms = {r["term"] for r in self.books[("FR", "accounting")]["market_specific"]["fr"]}
        self.assertTrue(any("cabinet" in t or "expertise" in t for t in fr_terms))
        self.assertFalse(any("fiduciaire" in t for t in fr_terms))

    def test_market_comparison_stays_within_one_language(self):
        be_fr = {r["term"] for r in self.books[("BE", "accounting")]["market_specific"]["fr"]}
        self.assertFalse(any(w in t for t in be_fr for w in ("boekhouding", "btw", "klanten")))

    def test_personal_data_is_measured_not_listed_as_a_convention(self):
        be = self.books[("BE", "accounting")]
        self.assertGreater(be["personal_data"]["date_of_birth"], 0.2)
        be_fr = {r["term"] for r in be["market_specific"]["fr"]}
        self.assertFalse(any("naissance" in t for t in be_fr))

    def test_outcomes_need_enough_evidence(self):
        self.assertEqual(self.books[("BE", "it-dev")]["what_wins"]["verdict"], "not yet known")

    def test_priors_survive_without_data(self):
        books = build_playbooks([], SEEDS)
        be = books[("BE", "accounting")]
        self.assertEqual(be["cvs"], 0)
        self.assertTrue(all(c["source"] == "PRIOR" for c in be["conventions"]))

    def test_check_flags_missing_conventions_and_personal_data(self):
        cv = "Comptable\nEXPÉRIENCE\nComptable dans une PME.\nDate de naissance : 01/01/1990\nFORMATION\nBachelier"
        issues = check_cv(cv, self.books[("BE", "accounting")], SEEDS[("BE", "accounting")])
        kinds = {(i["kind"], i["what"]) for i in issues}
        self.assertIn(("ask", "ITAA status"), kinds)
        self.assertIn(("remove", "date of birth"), kinds)


if __name__ == "__main__":
    unittest.main()
