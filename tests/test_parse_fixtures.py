"""Fixture tests over preserved G0 raw captures (probe/raw/).

These verify the parsers against real CNMV pages — no network.
"""
import os
import re
import sqlite3
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import cnmv, store

FIX_NOD_PAGE = os.path.join(ROOT, "probe", "raw", "run-20260914T035225Z",
                            "00003.html")
FIX_ANULADAS = os.path.join(ROOT, "probe", "raw", "run-20260914T035225Z",
                            "00137.html")
FIX_EMPTY_ANULADAS = os.path.join(ROOT, "probe", "raw", "run-20260914T035225Z",
                                  "00205.html")


class TestNodListParsing(unittest.TestCase):
    def setUp(self):
        self.html = open(FIX_NOD_PAGE, encoding="utf-8",
                         errors="replace").read()

    def test_ten_blocks_with_registry_numbers(self):
        blocks = re.findall(
            r'repListaPrincipal_ctl\d+_elementoPrimerNivel.*?</li>\s*</ul>',
            self.html, re.S)
        self.assertEqual(len(blocks), 10)
        regs = [re.search(r'registro:\s*(\d+)', b).group(1) for b in blocks]
        self.assertTrue(all(re.fullmatch(r"\d{9,10}", r) for r in regs))

    def test_explicit_rectification_relation(self):
        self.assertRegex(self.html,
                         r'rectifica a nº de registro:\s*2026113065')

    def test_doc_tokens_present(self):
        toks = re.findall(r'verdocumento/ver\?e=([^"\'&]+)', self.html)
        self.assertEqual(len(toks), 10)


class TestAnuladasParsing(unittest.TestCase):
    def test_explicit_annulment(self):
        t = cnmv.clean(re.sub(
            r"<[^>]+>", " ", open(FIX_ANULADAS, encoding="utf-8",
                                  errors="replace").read()))
        m = re.search(r"registro de entrada\s*(\d{9,10})\s*anula", t)
        self.assertEqual(m.group(1), "2021035057")
        self.assertIn(("2021034475", "17/03/2021"),
                      re.findall(r"(\d{9,10})\s*de\s*(\d{2}/\d{2}/\d{4})", t))

    def test_empty_annulment_page_yields_no_relation(self):
        t = cnmv.clean(re.sub(
            r"<[^>]+>", " ", open(FIX_EMPTY_ANULADAS, encoding="utf-8",
                                  errors="replace").read()))
        self.assertIsNone(
            re.search(r"registro de entrada\s*(\d{9,10})\s*anula", t))


class TestDimensions(unittest.TestCase):
    def test_surface_type_never_promoted_without_basis(self):
        self.assertEqual(store.SURFACE_TYPE_DEFAULT["ps"],
                         ("UNCLASSIFIED", "NONE"))
        self.assertEqual(store.SURFACE_TYPE_DEFAULT["nod"][0],
                         "PDMR_TRANSACTION")

    def test_content_hash_excludes_observation_context(self):
        self.assertIn("source_url_observed", store._CONTENT_EXCLUDED)


if __name__ == "__main__":
    unittest.main()
