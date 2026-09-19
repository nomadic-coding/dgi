# -*- coding: utf-8 -*-

import os
import unittest
from urllib.parse import urlsplit

from odoo.tests import tagged
from odoo.tests.common import _super_send

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
@unittest.skipUnless(
    os.environ.get("HKA_USER") and os.environ.get("HKA_PASS"),
    "Set HKA_USER and HKA_PASS to run live HKA tests",
)
class TestL10nPaEdiLiveHka(L10nPaEdiTestCommon):
    """Send the locked invoice shapes to the real HKA demo API."""

    @classmethod
    def _request_handler(cls, s, r, /, **kw):
        hostname = urlsplit(r.url).hostname or ""
        if hostname.endswith("thefactoryhka.com.pa"):
            return _super_send(s, r, **kw)
        return super()._request_handler(s, r, **kw)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.write({
            "hka_api_url": os.environ.get(
                "HKA_URL", "https://demointegracion.thefactoryhka.com.pa"
            ),
            "hka_usuario": os.environ["HKA_USER"],
            "hka_clave": os.environ["HKA_PASS"],
            "hka_timeout": 60,
            "hka_verify_ssl": True,
        })
        address = cls._panama_address_vals()
        cls.partner_live_contribuyente = cls.env["res.partner"].create({
            **address,
            "name": "EKOMERCIO",
            "is_company": False,
            "vat": "8-123-456",
            "dgi_ruc": "8-123-456",
            "dgi_tipo_ruc": "01",
            "dgi_dv": "91",
            "dgi_razon_social": "EKOMERCIO",
            "email": "ekomercio@example.com",
        })
        cls.partner_live_contribuyente._dgi_set_ruc_validated({
            "vat": "8-123-456",
            "dgi_dv": "91",
            "dgi_razon_social": "EKOMERCIO",
        })

    def _assert_hka_accepted(self, move, expected_number):
        self.assertEqual(move.name, expected_number)
        self.assertTrue(
            move.dgi_sent,
            "HKA rejected %s: %s" % (move.name, move.dgi_error_message),
        )
        self.assertTrue(move.dgi_cufe)
        self.assertIn(move.dgi_status, ("procesado", "Procesado"))

    @unittest.skipUnless(
        os.environ.get("HKA_LIVE_BASIC"),
        "Set HKA_LIVE_BASIC=1 to send the 337-339 live invoices",
    )
    def test_live_invoices_accepted_by_hka(self):
        self.dgi_sequence.sudo().write({"number_next": 337})
        invoice_date = "2026-09-06"

        contribuyente = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
        )
        self.assertEqual(contribuyente.name, "0000000337")
        contribuyente.action_send_to_dgi()
        self._assert_hka_accepted(contribuyente, "0000000337")

        consumidor = self._create_dgi_invoice(
            partner=self.partner_consumidor_final,
            invoice_date=invoice_date,
        )
        self.assertEqual(consumidor.name, "0000000338")
        consumidor.action_send_to_dgi()
        self._assert_hka_accepted(consumidor, "0000000338")

        credit_note = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            move_type="out_refund",
            reversed_entry=contribuyente,
        )
        self.assertEqual(credit_note.name, "0000000339")
        credit_note.action_send_to_dgi()
        self._assert_hka_accepted(credit_note, "0000000339")

    @unittest.skipUnless(
        os.environ.get("HKA_LIVE_DEDUCT"),
        "Set HKA_LIVE_DEDUCT=1 to send the 340-342 deduction invoices",
    )
    def test_live_deduction_invoices_accepted_by_hka(self):
        """Send the down-payment remainder and a negative-discount invoice to HKA."""
        self.dgi_sequence.sudo().write({"number_next": 340})
        invoice_date = "2026-09-06"
        _sale, downpayment, final = self._create_sale_final_invoice_with_downpayment(
            partner=self.partner_live_contribuyente,
            downpayment_date=invoice_date,
            final_date=invoice_date,
        )
        self.assertEqual(downpayment.name, "0000000340")
        self.assertEqual(final.name, "0000000341")
        self._assert_hka_payload_deducts_negative_lines(final, 1000.0)

        downpayment.action_send_to_dgi()
        self._assert_hka_accepted(downpayment, "0000000340")
        final.action_send_to_dgi()
        self._assert_hka_accepted(final, "0000000341")

        discount = self._create_negative_discount_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
        )
        self.assertEqual(discount.name, "0000000342")
        self._assert_hka_payload_deducts_negative_lines(discount, 1000.0)
        discount.action_send_to_dgi()
        self._assert_hka_accepted(discount, "0000000342")

    @unittest.skipUnless(
        os.environ.get("HKA_LIVE_MERGE"),
        "Set HKA_LIVE_MERGE=1 to send the 343-344 merged invoices",
    )
    def test_live_merged_rounding_invoices_accepted_by_hka(self):
        """Send merged same-code lines as quantity 1 with the net total as unit price."""
        self.dgi_sequence.sudo().write({"number_next": 343})
        invoice_date = "2026-09-06"

        uneven = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                {**self._default_invoice_line_vals(), "name": "Line A", "quantity": 1, "price_unit": 10.00},
                {**self._default_invoice_line_vals(), "name": "Line B", "quantity": 1, "price_unit": 10.00},
                {**self._default_invoice_line_vals(), "name": "Line C", "quantity": 1, "price_unit": 10.01},
            ],
        )
        self.assertEqual(uneven.name, "0000000343")
        payload = uneven._prepare_dgi_document_data()
        self.assertEqual(len(payload["documento"]["listaItems"]), 1)
        self.assertEqual(payload["documento"]["listaItems"][0]["cantidad"], "1.00")
        self.assertEqual(payload["documento"]["listaItems"][0]["precioUnitario"], "30.01")
        self._assert_hka_payload_matches_move(uneven, payload)
        uneven.action_send_to_dgi()
        self._assert_hka_accepted(uneven, "0000000343")

        pennies = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                {
                    **self._default_invoice_line_vals(),
                    "name": "Penny %s" % index,
                    "quantity": 1,
                    "price_unit": 0.33,
                }
                for index in range(7)
            ],
        )
        self.assertEqual(pennies.name, "0000000344")
        payload = pennies._prepare_dgi_document_data()
        self.assertEqual(payload["documento"]["listaItems"][0]["cantidad"], "1.00")
        self.assertEqual(payload["documento"]["listaItems"][0]["precioUnitario"], "2.31")
        self._assert_hka_payload_matches_move(pennies, payload)
        pennies.action_send_to_dgi()
        self._assert_hka_accepted(pennies, "0000000344")

    @unittest.skipUnless(
        os.environ.get("HKA_LIVE_ZERO"),
        "Set HKA_LIVE_ZERO=1 to send the 345-347 zero-tax invoices",
    )
    def test_live_zero_tax_invoices_accepted_by_hka(self):
        """Send 0% ITBMS invoices: single line, merged lines, and mixed 0%/7%."""
        self.dgi_sequence.sudo().write({"number_next": 345})
        invoice_date = "2026-09-06"

        single = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[self._zero_rate_invoice_line_vals()],
        )
        self.assertEqual(single.name, "0000000345")
        payload = single._prepare_dgi_document_data()
        self.assertEqual(payload["documento"]["listaItems"][0]["tasaITBMS"], "00")
        self.assertEqual(payload["documento"]["listaItems"][0]["valorITBMS"], "0.00")
        self._assert_hka_payload_matches_move(single, payload)
        single.action_send_to_dgi()
        self._assert_hka_accepted(single, "0000000345")

        merged = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                self._zero_rate_invoice_line_vals(
                    name="Exempt A", quantity=1, price_unit=10.00
                ),
                self._zero_rate_invoice_line_vals(
                    name="Exempt B", quantity=1, price_unit=10.00
                ),
                self._zero_rate_invoice_line_vals(
                    name="Exempt C", quantity=1, price_unit=10.01
                ),
            ],
        )
        self.assertEqual(merged.name, "0000000346")
        payload = merged._prepare_dgi_document_data()
        item = payload["documento"]["listaItems"][0]
        self.assertEqual(len(payload["documento"]["listaItems"]), 1)
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "30.01")
        self.assertEqual(item["tasaITBMS"], "00")
        self.assertEqual(item["valorITBMS"], "0.00")
        self._assert_hka_payload_matches_move(merged, payload)
        merged.action_send_to_dgi()
        self._assert_hka_accepted(merged, "0000000346")

        mixed = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                self._zero_rate_invoice_line_vals(name="Exempt consulting"),
                self._default_invoice_line_vals(),
            ],
        )
        self.assertEqual(mixed.name, "0000000347")
        payload = mixed._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        self.assertEqual(len(items), 2)
        self.assertEqual({item["tasaITBMS"] for item in items}, {"00", "01"})
        self._assert_hka_payload_matches_move(mixed, payload)
        mixed.action_send_to_dgi()
        self._assert_hka_accepted(mixed, "0000000347")

    @unittest.skipUnless(
        os.environ.get("HKA_LIVE_MIX"),
        "Set HKA_LIVE_MIX=1 to send the 348-350 mixed-tax invoices",
    )
    def test_live_mixed_tax_invoices_accepted_by_hka(self):
        """Send same-DGI-code lines that must stay split by HKA tax code."""
        self.dgi_sequence.sudo().write({"number_next": 348})
        invoice_date = "2026-09-06"

        seven_and_ten = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Consulting 7%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Consulting 10%"
                ),
            ],
        )
        self.assertEqual(seven_and_ten.name, "0000000348")
        payload = seven_and_ten._prepare_dgi_document_data()
        self.assertEqual(len(payload["documento"]["listaItems"]), 2)
        self.assertEqual(
            {item["tasaITBMS"] for item in payload["documento"]["listaItems"]},
            {"01", "02"},
        )
        self._assert_hka_payload_matches_move(seven_and_ten, payload)
        seven_and_ten.action_send_to_dgi()
        self._assert_hka_accepted(seven_and_ten, "0000000348")

        merged_seven_plus_ten = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Seven A", quantity=1, price_unit=1000.0
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Seven B", quantity=1, price_unit=1000.0
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Ten", quantity=1, price_unit=1000.0
                ),
            ],
        )
        self.assertEqual(merged_seven_plus_ten.name, "0000000349")
        payload = merged_seven_plus_ten._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        self.assertEqual(len(items), 2)
        by_tasa = {item["tasaITBMS"]: item for item in items}
        self.assertEqual(by_tasa["01"]["cantidad"], "1.00")
        self.assertEqual(by_tasa["01"]["precioUnitario"], "2000.00")
        self.assertEqual(by_tasa["02"]["precioUnitario"], "1000.00")
        self._assert_hka_payload_matches_move(merged_seven_plus_ten, payload)
        merged_seven_plus_ten.action_send_to_dgi()
        self._assert_hka_accepted(merged_seven_plus_ten, "0000000349")

        three_tasas = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_0, name="Consulting 0%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Consulting 7%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Consulting 10%"
                ),
            ],
        )
        self.assertEqual(three_tasas.name, "0000000350")
        payload = three_tasas._prepare_dgi_document_data()
        self.assertEqual(len(payload["documento"]["listaItems"]), 3)
        self.assertEqual(
            {item["tasaITBMS"] for item in payload["documento"]["listaItems"]},
            {"00", "01", "02"},
        )
        self._assert_hka_payload_matches_move(three_tasas, payload)
        three_tasas.action_send_to_dgi()
        self._assert_hka_accepted(three_tasas, "0000000350")
