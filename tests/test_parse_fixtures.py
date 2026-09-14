"""Local-corpus fixture tests over preserved G0 raw captures (probe/raw/).

These verify the parsers against real CNMV pages — no network, but they
require the private raw corpus which is NOT redistributed with the repo.
They SKIP cleanly when the corpus is absent (clean clone / CI).
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import cnmv, store

RUN_DIR = os.path.join(ROOT, "probe", "raw", "run-20260914T035225Z")
FIX_NOD_PAGE = os.path.join(RUN_DIR, "00003.html")
FIX_ANULADAS = os.path.join(RUN_DIR, "00137.html")
FIX_EMPTY_ANULADAS = os.path.join(RUN_DIR, "00205.html")

CORPUS_AVAILABLE = all(os.path.isfile(p) for p in
                       (FIX_NOD_PAGE, FIX_ANULADAS, FIX_EMPTY_ANULADAS))
SKIP_MSG = "LOCAL_CNMV_CORPUS_NOT_AVAILABLE"


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


@unittest.skipUnless(CORPUS_AVAILABLE, SKIP_MSG)
class TestNodListParsing(unittest.TestCase):
    def setUp(self):
        self.html = _read(FIX_NOD_PAGE)

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


@unittest.skipUnless(CORPUS_AVAILABLE, SKIP_MSG)
class TestAnuladasParsing(unittest.TestCase):
    def test_explicit_annulment(self):
        t = cnmv.clean(re.sub(r"<[^>]+>", " ", _read(FIX_ANULADAS)))
        m = re.search(r"registro de entrada\s*(\d{9,10})\s*anula", t)
        self.assertEqual(m.group(1), "2021035057")
        self.assertIn(("2021034475", "17/03/2021"),
                      re.findall(r"(\d{9,10})\s*de\s*(\d{2}/\d{2}/\d{4})", t))

    def test_empty_annulment_page_yields_no_relation(self):
        t = cnmv.clean(re.sub(r"<[^>]+>", " ", _read(FIX_EMPTY_ANULADAS)))
        self.assertIsNone(
            re.search(r"registro de entrada\s*(\d{9,10})\s*anula", t))


class TestDimensions(unittest.TestCase):
    """Pure-model tests — always available, no corpus needed."""

    def test_surface_type_never_promoted_without_basis(self):
        self.assertEqual(store.SURFACE_TYPE_DEFAULT["ps"],
                         ("UNCLASSIFIED", "NONE"))

    def test_nod_surface_is_notification_not_transaction(self):
        # A NOD notice is a *notification* that may carry 1..N
        # transactions; the surface label must not pre-empt the
        # event-level semantics (G2 model correction).
        self.assertEqual(store.SURFACE_TYPE_DEFAULT["nod"],
                         ("PDMR_NOTIFICATION", "SURFACE_DEFAULT"))

    def test_content_hash_excludes_observation_context(self):
        self.assertIn("source_url_observed", store._CONTENT_EXCLUDED)


if __name__ == "__main__":
    unittest.main()
