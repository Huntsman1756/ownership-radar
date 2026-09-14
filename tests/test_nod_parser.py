"""Unit tests for the G2 NOD parser — synthetic line fixtures only.

Fixtures mimic the line/cell stream produced by extract_lines() but are
hand-written: no real CNMV document content is redistributed and no PDF
dependency is needed for the public suite.
"""
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import nodpdf, store


def mk_pages(lines):
    """A synthetic document: one page, each entry = one line of cells."""
    return [lines]


HEADER = [
    ["MODELO DE NOTIFICACIÓN DE LAS OPERACIONES"],
    ["STANDARD FORM FOR NOTIFICATION AND PUBLIC DISCLOSURE"],
    ["1. DATOS DE LA PERSONA", "DETAILS OF THE PERSON"],
    ["a) Nombre y apellidos - Razón social | Name and surname"],
    ["JUAN EJEMPLO PÉREZ"],
    ["2. MOTIVO DE LA NOTIFICACIÓN | REASON FOR THE NOTIFICATION"],
    ["[ √ ] Persona con responsabilidad de dirección | PDMR"],
    ["[ ] Persona estrechamente vinculada | Person closely associated"],
    ["a) Cargo - posición | Job title"],
    ["CONSEJERO"],
    ["b) Notificación inicial - Modificación | Initial - Amendment"],
    ["Inicial"],
    ["3. DATOS DEL EMISOR | DETAILS OF THE ISSUER"],
    ["a) Identificación | Name:"],
    ["EMISOR DE PRUEBA, S.A."],
    ["b) LEI:"],
    ["959800EXAMPLE000000001"],
    ["4. DATOS DE LA OPERACIÓN | DETAILS OF THE TRANSACTIONS"],
    ["Código de Identificación", "Naturaleza del instrumento",
     "Naturaleza de la operación", "Fecha", "Lugar", "Volumen",
     "Precio Unitario", "Divisa"],
    ["4.a)", "4.b)", "4.c)", "4.d)", "4.e)", "4.f)", "4.g)", "4.h)"],
]
AGG = [["Total Agregado"], ["..."], ["Aggregated information"], ["5)"]]


def doc(rows, tail=None):
    return mk_pages(HEADER + rows + AGG + (tail or []) +
                    [["Otra información | Additional information"]])


class TestGridParsing(unittest.TestCase):
    def test_multi_execution_event(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "100,00", "10,50", "EUR"],
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "200,00", "10,00", "EUR"],
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "50,00", "11,00", "EUR"],
        ], tail=[["350,00", "10,3571"]]))
        self.assertEqual(r["parse_status"], nodpdf.PARSED)
        self.assertEqual(len(r["events"]), 1)
        ev = r["events"][0]
        self.assertEqual(len(ev["executions"]), 3)
        self.assertEqual(ev["computed_volume"], "350.00")
        self.assertEqual(ev["aggregate_qa"], "MATCH")
        self.assertEqual(ev["declared_aggregate_volume"], "350,00")

    def test_multi_event_notice(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "100,00", "10,00", "EUR"],
            ["ES0000000001", "Acción", "Compra", "02/03/2025", "XMAD",
             "50,00", "10,00", "EUR"],
        ], tail=[["150,00", "10,00"]]))
        self.assertEqual(len(r["events"]), 2)
        self.assertEqual([e["transaction_date_raw"] for e in r["events"]],
                         ["01/03/2025", "02/03/2025"])

    def test_aggregate_is_not_additional_transaction(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Acción", "Venta", "01/03/2025", "XMAD",
             "10,00", "5,00", "EUR"],
        ], tail=[["10,00", "5,00"]]))
        ev = r["events"][0]
        self.assertEqual(len(ev["executions"]), 1)
        self.assertIsNotNone(ev["aggregate"])
        self.assertEqual(ev["aggregate_qa"], "MATCH")

    def test_decimal_exact_no_float(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XOFF",
             "0,10", "0,10", "EUR"],
        ], tail=[["0,10", "0,10"]]))
        e = r["events"][0]["executions"][0]
        self.assertIsInstance(e["price"], Decimal)
        self.assertIsInstance(e["volume"], Decimal)
        self.assertEqual(e["price"], Decimal("0.10"))
        self.assertEqual(e["volume_raw"], "0,10")   # raw preserved

    def test_transaction_nature_conservative(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Acción", "Venta", "01/03/2025", "XMAD",
             "10,00", "5,00", "EUR"],
            ["ES0000000001", "Acción", "Entrega gratuita", "02/03/2025",
             "XMAD", "10,00", "0,00", "EUR"],
        ], tail=[["20,00", "2,50"]]))
        self.assertEqual(r["events"][0]["transaction_nature_normalized"],
                         "SELL")
        self.assertIsNone(
            r["events"][1]["transaction_nature_normalized"])
        self.assertEqual(r["events"][1]["transaction_nature_raw"],
                         "Entrega gratuita")

    def test_xoff_is_outside_trading_venue(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Derivados", "Otros", "01/03/2025", "XOFF",
             "10,00", "0,00", "EUR"],
        ], tail=[["10,00", "0,00"]]))
        self.assertEqual(r["events"][0]["outside_trading_venue"], "TRUE")
        self.assertEqual(r["events"][0]["venue_code_raw"], "XOFF")


class TestHeaderParsing(unittest.TestCase):
    def test_amendment_with_explanation(self):
        lines = [l[:] for l in HEADER]
        i = lines.index(["Inicial"])
        lines[i] = ["Modificación"]
        lines.insert(i + 1, ["Se corrige el volumen de la operación"])
        r = nodpdf.parse_lines(mk_pages(lines + [
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "10,00", "5,00", "EUR"]] + AGG + [["10,00", "5,00"]] +
            [["Otra información | Additional information"]]))
        self.assertEqual(r["notification_kind"], "AMENDMENT")
        self.assertEqual(r["amendment_text_raw"],
                         "Se corrige el volumen de la operación")

    def test_closely_associated_legal_person(self):
        lines = [l[:] for l in HEADER]
        lines[6] = ["[ ] Persona con responsabilidad de dirección | PDMR"]
        lines[7] = ["[ √ ] Persona estrechamente vinculada | Person closely associated"]
        lines[4] = ["VEHÍCULO INVERSOR, S.A."]
        lines[9] = ["JUAN EJEMPLO PÉREZ - CONSEJERO"]
        r = nodpdf.parse_lines(mk_pages(lines + [
            ["4. DATOS DE LA OPERACIÓN | DETAILS OF THE TRANSACTIONS"]] +
            [["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
              "10,00", "5,00", "EUR"]] + AGG + [["10,00", "5,00"]]))
        self.assertEqual(r["closely_associated"], "TRUE")
        self.assertEqual(r["notifying_party_kind"], "LEGAL_PERSON")
        self.assertEqual(r["notifying_party_name_raw"],
                         "VEHÍCULO INVERSOR, S.A.")
        self.assertEqual(r["related_pdmr_name_raw"], "JUAN EJEMPLO PÉREZ")
        self.assertEqual(r["related_pdmr_position_raw"], "CONSEJERO")

    def test_ca_unsplittable_pdmr_field_fails_closed(self):
        lines = [l[:] for l in HEADER]
        lines[7] = ["[ √ ] Persona estrechamente vinculada"]
        lines[6] = ["[ ] Persona con responsabilidad de dirección"]
        lines[9] = ["CONSEJERO"]   # present but no name/position separator
        r = nodpdf.parse_lines(mk_pages(lines + [
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "10,00", "5,00", "EUR"]] + AGG + [["10,00", "5,00"]]))
        self.assertEqual(r["parse_status"],
                         nodpdf.PARSED_UNMAPPED)
        self.assertIn("related_pdmr_unsplittable", r["unmapped"])

    def test_pdmr_is_natural_person(self):
        r = nodpdf.parse_lines(doc([
            ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
             "10,00", "5,00", "EUR"]], tail=[["10,00", "5,00"]]))
        self.assertEqual(r["closely_associated"], "FALSE")
        self.assertEqual(r["notifying_party_kind"], "NATURAL_PERSON")
        self.assertEqual(r["issuer_lei_document"],
                         "959800EXAMPLE000000001")


class TestFailClosed(unittest.TestCase):
    def test_unsupported_template(self):
        r = nodpdf.parse_lines(mk_pages([["CIRCULAR 8/2015 MODELO III"]]))
        self.assertEqual(r["parse_status"], nodpdf.UNSUPPORTED_TEMPLATE)

    def test_no_text_layer(self):
        r = nodpdf.parse_lines(mk_pages([]))
        self.assertEqual(r["parse_status"], nodpdf.UNSUPPORTED_NO_TEXT)

    def test_same_input_same_output(self):
        rows = [["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
                 "10,00", "5,00", "EUR"]]
        a = nodpdf.parse_lines(doc(rows, tail=[["10,00", "5,00"]]))
        b = nodpdf.parse_lines(doc(rows, tail=[["10,00", "5,00"]]))
        self.assertEqual(a, b)


class TestStorage(unittest.TestCase):
    def test_event_provenance_and_shape(self):
        import sqlite3, tempfile
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            cx = store.init_db(path)
            p = nodpdf.parse_lines(doc([
                ["ES0000000001", "Acción", "Compra", "01/03/2025", "XMAD",
                 "10,00", "5,00", "EUR"]], tail=[["10,00", "5,00"]]))
            p["doc_sha256"] = "ab" * 32
            store.store_semantic(cx, "nod:2099000001", p, "dev")
            ev = cx.execute("SELECT * FROM transaction_event").fetchone()
            self.assertEqual(ev[0], "nod:2099000001:00")
            lines = cx.execute(
                "SELECT * FROM execution_line WHERE event_id=?",
                (ev[0],)).fetchall()
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0][3], "5.00")   # exact decimal text
            sem = cx.execute("SELECT doc_sha256, semantic_parser_version "
                             "FROM nod_notice_semantic").fetchone()
            self.assertEqual(sem[0], "ab" * 32)
            self.assertEqual(sem[1], nodpdf.SEMANTIC_PARSER_VERSION)
            cx.close()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
