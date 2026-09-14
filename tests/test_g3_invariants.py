"""G3 invariant tests — synthetic positioned-line fixtures only.

Same approach as test_nod_parser.py: hand-written lines of positioned
cells ({"x0","x1","t"}), no real CNMV document content and no PDF
dependency. The invariants encode the G3 contract:

  * a significant-holding notice is a POSITION disclosure — the parser
    must never emit invented transactions;
  * financial instruments are never collapsed into share rows;
  * a declared aggregate is never overwritten by a computed value;
  * percentages carry their regulatory generation (pre/post C2/2022);
  * loyalty fields cannot appear under pre-2022 semantics;
  * AC acquisitions and disposals stay separate (no netting);
  * the 1% trigger is a declared checkbox, never recomputed;
  * resulting treasury stock != operation flow;
  * identical input + identical parser version = identical output.
"""
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ownership_radar import pspdf, acpdf, g3pdf as g  # noqa: E402


def L(*texts, xs=None):
    """One visual line of positioned cells."""
    cells = []
    for i, t in enumerate(texts):
        x = float(xs[i]) if xs else i * 60.0
        cells.append({"x0": x, "x1": x + 40.0, "t": t})
    return cells


def PS_DOC(pct_total="5,000", loyalty=False):
    doc = [
        L("MODELO 1"),
        L("NOTIFICACIÓN DE PARTICIPACIONES SIGNIFICATIVAS"),
        L("STANDARD FORM FOR NOTIFICATION"),
        L("REGISTRO DE ENTRADA Nº 0001"),
        L("1. IDENTIFICACIÓN DEL EMISOR"),
        L("EMISOR PRUEBA, S.A."),
        L("2. MOTIVO DE LA NOTIFICACIÓN"),
        L("[ √ ] Adquisición o transmisión de derechos de voto"),
        L("[ ] Adquisición o transmisión de instrumentos financieros"),
        L("[ ] Modificación en el número de derechos de voto"),
        L("[ ] Otros motivos"),
        L("3. PERSONA O ENTIDAD OBLIGADA"),
        L("Apellidos y nombre o denominación social"),
        L("SUJETO PRUEBA, S.A."),
        L("Ciudad y país del domicilio"),
        L("MADRID, ESPAÑA"),
        L("5. Fecha en la que se cruzó el umbral"),
        L("15/03/2019"),
        L("6. Situación resultante tras el hecho motivo"),
        L("4,500", "0,500", pct_total, "1.000.000"),
        L("Posición de la notificación previa"),
        L("3,000", "0,000", "3,000"),
        L("7.A. Derechos de voto atribuidos a acciones"),
        L("Directo", "Indirecto", "Directo", "Indirecto",
          xs=[100, 200, 300, 400]),
        L("ES0000000001", "45.000", "4,500", xs=[50, 100, 300]),
        L("SUBTOTAL 7.A", "45.000", "4,500"),
        L("7.B.1. INSTRUMENTOS FINANCIEROS 13(1)(A)"),
        L("Tipo de instrumento", "Fecha última", "Número de",
          "% derechos"),
        L("Opción", "01/01/2020", "5.000", "0,500",
          xs=[50, 150, 300, 400]),
        L("SUBTOTAL 7.B.1", "5.000", "0,500"),
        L("8. INFORMACIÓN SOBRE EL SUJETO OBLIGADO"),
        L("[ √ ] No está controlado"),
        L("9. DERECHOS DE VOTO RECIBIDOS EN REPRESENTACIÓN"),
        L("10. INFORMACIÓN ADICIONAL"),
        L("LUGAR Y FECHA DE LA NOTIFICACIÓN"),
        L("MADRID, 20/03/2019"),
    ]
    if loyalty:
        doc.insert(3, L("11. VOTO DOBLE POR LEALTAD"))
        doc.insert(4, L("11.A Voto doble por lealtad"))
        doc.insert(5, L("SUBTOTAL 11.A"))
    return [doc]


def AC_DOC():
    """Modelo 4 treasury notice: 1 acquisition + 1 disposal, totals,
    final position. Column anchors mirror the CNMV grid order."""
    return [[
        L("MODELO 4"),
        L("NOTIFICACIÓN DE OPERACIONES SOBRE ACCIONES PROPIAS"),
        L("STANDARD FORM"),
        L("REGISTRO DE ENTRADA Nº 0002"),
        L("1. IDENTIFICACIÓN DEL EMISOR"),
        L("NIF | TAX ID", "A39000013"),
        L("DENOMINACIÓN SOCIAL | COMPANY NAME"),
        L("EMISOR PRUEBA, S.A."),
        L("1.000.000.000"),
        L("DERECHOS DE VOTO | VOTING RIGHTS"),
        L("2. MOTIVO DE LA NOTIFICACIÓN"),
        L("[ ] Primera admisión a cotización"),
        L("[ √ ] Umbral del 1% de adquisiciones"),
        L("[ ] Actualización sobrevenida"),
        L("3. FECHA QUE MOTIVA LA NOTIFICACIÓN"),
        L("31/03/2021"),
        L("4. DETALLE DE LAS OPERACIONES"),
        L("Directas", "Precio", "Indirectas", "Precio",
          "Directos", "Indirectos", "Directos", "Indirectos",
          xs=[100, 160, 220, 280, 340, 400, 460, 520]),
        L("01/03/2021", "A", "ES0113900J37", "1.000", "10,50",
          "1.000", "0,001", xs=[0, 30, 55, 100, 160, 340, 460]),
        L("02/03/2021", "T", "ES0113900J37", "500", "10,60",
          "500", "0,000", xs=[0, 30, 55, 100, 160, 340, 460]),
        L("Total adquisición", "1.000", "0,001", xs=[0, 340, 460]),
        L("Total transmisión", "500", "0,000", xs=[0, 340, 460]),
        L("5. POSESIÓN FINAL DE AUTOCARTERA"),
        L("Directas", "Indirectas", "Directos", "Indirectos",
          "Total", "Directos", "Indirectos", "Total",
          xs=[100, 160, 220, 280, 340, 400, 460, 520]),
        L("ES0113900J37", "1.500", "1.500", "1.500", "0,002",
          "0,002", xs=[0, 100, 220, 340, 400, 520]),
        L("6. IDENTIFICACIÓN DE LA POSICIÓN INDIRECTA"),
        L("7. DETALLE DE LA CADENA"),
        L("8. INFORMACIÓN ADICIONAL"),
        L("LUGAR Y FECHA DE LA NOTIFICACIÓN"),
        L("MADRID, 01/04/2021"),
    ]]


class TestPsInvariants(unittest.TestCase):

    def test_ps_parses_position_disclosure_not_trade(self):
        r = pspdf.parse_lines(PS_DOC())
        self.assertEqual(r["parse_status"], g.PARSED)
        self.assertEqual(r["regulatory_template"], g.T_MODEL_1_C8)
        # position disclosure: no transaction/event object may exist
        for k in r:
            self.assertNotIn("transaction", k)
            self.assertNotIn("event", k)
            self.assertNotIn("operation", k)
            self.assertNotIn("trade", k)
        self.assertEqual(r["obliged_subject_name_raw"],
                         "SUJETO PRUEBA, S.A.")
        self.assertEqual(r["threshold_date"], "2019-03-15")
        pc = r["position_current"]
        self.assertEqual(pc["pct_shares_raw"], "4,500")
        self.assertEqual(pc["pct_total_raw"], "5,000")
        self.assertEqual(r["issuer_total_voting_rights"], 1000000)
        self.assertEqual(r["position_previous"]["pct_total_raw"],
                         "3,000")
        self.assertTrue(r["reason_voting_rights"])
        self.assertFalse(r["reason_instruments"])

    def test_ps_instruments_not_collapsed_into_shares(self):
        r = pspdf.parse_lines(PS_DOC())
        self.assertEqual(len(r["shares_rows"]), 1)
        self.assertEqual(len(r["instruments_a_rows"]), 1)
        inst = r["instruments_a_rows"][0]
        self.assertEqual(inst["instrument_type_raw"], "Opción")
        self.assertEqual(inst["expiration_date"], "2020-01-01")
        self.assertEqual(inst["voting_rights"], 5000)
        self.assertEqual(inst["pct"], "0.500")
        # the instrument's voting rights must NOT appear as shares
        self.assertEqual(r["shares_rows"][0]["vr_direct"], 45000)
        self.assertEqual(r["instruments_a_subtotal"]["voting_rights"],
                         5000)

    def test_ps_wrapped_instrument_type_merges(self):
        doc = PS_DOC()
        # wrap the B1 row across three visual lines
        doc = [doc[0][:22] + [
            L("7.B.1. INSTRUMENTOS FINANCIEROS 13(1)(A)"),
            L("Tipo de instrumento", "Fecha última"),
            L("Contingent Sale and", xs=[50]),
            L("Purchase Agreement", xs=[50]),
            L("05/03/2025", "287.522.907", "5,000",
              xs=[150, 300, 400]),
            L("SUBTOTAL 7.B.1", "287.522.907", "5,000"),
        ] + doc[0][26:]]
        r = pspdf.parse_lines(doc)
        self.assertEqual(len(r["instruments_a_rows"]), 1)
        self.assertEqual(r["instruments_a_rows"][0]
                         ["instrument_type_raw"],
                         "Contingent Sale and Purchase Agreement")
        self.assertEqual(r["instruments_a_rows"][0]["voting_rights"],
                         287522907)

    def test_ps_declared_aggregate_never_overwritten(self):
        r = pspdf.parse_lines(PS_DOC(pct_total="5,100"))
        self.assertEqual(r["aggregate_qa"],
                         "DECLARED_COMPUTED_MISMATCH")
        # declared values stay exactly as sourced
        self.assertEqual(r["position_current"]["pct_total_raw"],
                         "5,100")
        self.assertEqual(r["position_current"]["pct_total"], "5.100")

    def test_ps_percentage_semantics_generation(self):
        pre = pspdf.parse_lines(PS_DOC())
        post = pspdf.parse_lines(PS_DOC(loyalty=True))
        self.assertEqual(pre["percentage_semantics"],
                         pspdf.SEM_PRE)
        self.assertEqual(pre["loyalty_section_present"], False)
        self.assertEqual(post["regulatory_template"], g.T_MODEL_1_C2)
        self.assertEqual(post["percentage_semantics"],
                         pspdf.SEM_POST)
        self.assertEqual(post["loyalty_section_present"], True)

    def test_ps_loyalty_fields_cannot_be_pre2022(self):
        # the C8/2015 fingerprint and the loyalty-section anchor share
        # the same trigger word, so loyalty semantics can only ever
        # attach to CIRC_2_2022_MODEL_1 — never to pre-2022 output
        r = pspdf.parse_lines(PS_DOC())
        self.assertEqual(r["regulatory_template"], g.T_MODEL_1_C8)
        self.assertEqual(r["percentage_semantics"], pspdf.SEM_PRE)
        self.assertFalse(r["loyalty_section_present"])
        self.assertEqual(r["loyalty_11a_rows"], [])
        self.assertEqual(r["loyalty_11b_rows"], [])
        self.assertIsNone(r["loyalty_11a"])

    def test_ps_unsupported_and_no_text_fail_closed(self):
        self.assertEqual(
            pspdf.parse_lines([[]])["parse_status"],
            g.UNSUPPORTED_NO_TEXT)
        mono = [[L("MODELO I"), L("PARTICIPACIONES SIGNIFICATIVAS")]]
        self.assertEqual(
            pspdf.parse_lines(mono)["parse_status"],
            g.UNSUPPORTED_LEGACY)

    def test_ps_deterministic(self):
        a = pspdf.parse_lines(PS_DOC())
        b = pspdf.parse_lines(copy.deepcopy(PS_DOC()))
        self.assertEqual(a, b)


class TestAcInvariants(unittest.TestCase):

    def test_ac_flow_stock_trigger_three_layers(self):
        r = acpdf.parse_lines(AC_DOC())
        self.assertEqual(r["parse_status"], g.PARSED)
        self.assertEqual(r["regulatory_template"], g.T_MODEL_4)
        # FLOW: two operations, normalized flags, no netting
        self.assertEqual(len(r["operations"]), 2)
        self.assertEqual(r["operations"][0]["operation_flag_normalized"],
                         "ACQUISITION")
        self.assertEqual(r["operations"][1]["operation_flag_normalized"],
                         "DISPOSAL")
        self.assertEqual(r["operations"][0]["shares_direct"], 1000)
        self.assertEqual(r["operations"][0]["price_direct"], "10.50")
        self.assertEqual(r["operations"][1]["shares_direct"], 500)
        # STOCK: resulting position is separate from the flow
        fp = r["final_position"]
        self.assertIsNotNone(fp)
        self.assertEqual(fp["vr_total"], 1500)
        self.assertEqual(fp["pct_total"], "0.002")
        # TRIGGER: declared checkbox, never recomputed
        self.assertEqual(r["reason_acquisitions_1pct"], True)
        self.assertEqual(r["reason_first_admission"], False)

    def test_ac_disposals_never_netted_against_acquisitions(self):
        r = acpdf.parse_lines(AC_DOC())
        qa = r["operations_flow_qa"]
        self.assertEqual(qa["acquisitions"]["status"], "MATCH")
        self.assertEqual(qa["acquisitions"]["computed_vr_direct"],
                         "1000")
        # the disposal must not reduce the acquisition computation
        self.assertEqual(qa["transmissions"]["computed_vr_direct"],
                         "500")
        self.assertEqual(qa["transmissions"]["status"], "MATCH")
        # declared totals preserved as raw
        self.assertEqual(r["total_acquisitions"]["vr_direct_raw"],
                         "1.000")

    def test_ac_flow_qa_divergent_not_rewritten(self):
        doc = AC_DOC()
        # declared acquisition total disagrees with the op rows
        doc[0][22] = L("Total adquisición", "9.999", "0,999",
                       xs=[0, 340, 460])
        r = acpdf.parse_lines(doc)
        self.assertEqual(r["operations_flow_qa"]["acquisitions"]
                         ["status"], "DIVERGENT")
        self.assertEqual(r["total_acquisitions"]["vr_direct_raw"],
                         "9.999")

    def test_ac_resulting_position_is_not_flow(self):
        r = acpdf.parse_lines(AC_DOC())
        # final position (1500) != sum of acquisitions (1000):
        # both coexist as distinct layers
        self.assertNotEqual(
            r["final_position"]["vr_total"],
            r["operations_flow_qa"]["acquisitions"]
            ["computed_vr_direct"])

    def test_ac_deterministic(self):
        a = acpdf.parse_lines(AC_DOC())
        b = acpdf.parse_lines(copy.deepcopy(AC_DOC()))
        self.assertEqual(a, b)

    def test_ac_unsupported_families_fail_closed(self):
        self.assertEqual(
            acpdf.parse_lines([[]])["parse_status"],
            g.UNSUPPORTED_NO_TEXT)
        # a PS template parsed by the AC parser is unsupported,
        # never forced into the treasury model
        self.assertEqual(
            acpdf.parse_lines(PS_DOC())["parse_status"],
            g.UNSUPPORTED_TEMPLATE)


class TestG3Persistence(unittest.TestCase):
    """Semantic rows survive notice annulment (non-destructive)."""

    def test_annulled_notice_semantics_persist(self):
        import tempfile
        from ownership_radar import store
        with tempfile.TemporaryDirectory(
                ignore_cleanup_errors=True) as d:
            cx = store.init_db(os.path.join(d, "t.sqlite"))
            store.store_ps_semantic(cx, "ps:1",
                                    pspdf.parse_lines(PS_DOC()),
                                    corpus_split="dev")
            store.store_ac_semantic(cx, "ac:1",
                                    acpdf.parse_lines(AC_DOC()),
                                    corpus_split="dev")
            cx.execute(
                "INSERT INTO notice_relation"
                "(annulling_key, annulled_key, relation_type)"
                " VALUES(?,?,?)",
                ("ps:2", "ps:1", "ANNULS"))
            cx.execute(
                "INSERT INTO notice_relation"
                "(annulling_key, annulled_key, relation_type)"
                " VALUES(?,?,?)",
                ("ac:2", "ac:1", "ANNULS"))
            cx.commit()
            self.assertEqual(
                cx.execute("SELECT parse_status FROM "
                           "ps_notice_semantic WHERE notice_key='ps:1'")
                .fetchone()[0], g.PARSED)
            self.assertEqual(
                cx.execute("SELECT COUNT(*) FROM ps_instrument_row "
                           "WHERE notice_key='ps:1'").fetchone()[0], 1)
            self.assertEqual(
                cx.execute("SELECT COUNT(*) FROM ac_operation "
                           "WHERE notice_key='ac:1'").fetchone()[0], 2)
            self.assertEqual(
                cx.execute("SELECT COUNT(*) FROM notice_relation")
                .fetchone()[0], 2)
            cx.close()


if __name__ == "__main__":
    unittest.main()
