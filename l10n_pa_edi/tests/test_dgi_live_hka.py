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
        "Set HKA_LIVE_BASIC=1 to resend the original 286-288 live invoices",
    )
    def test_live_invoices_accepted_by_hka(self):
        self.dgi_sequence.sudo().write({"number_next": 286})
        invoice_date = "2026-09-05"

        contribuyente = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
        )
        self.assertEqual(contribuyente.name, "0000000286")
        contribuyente.action_send_to_dgi()
        self._assert_hka_accepted(contribuyente, "0000000286")

        consumidor = self._create_dgi_invoice(
            partner=self.partner_consumidor_final,
            invoice_date=invoice_date,
        )
        self.assertEqual(consumidor.name, "0000000287")
        consumidor.action_send_to_dgi()
        self._assert_hka_accepted(consumidor, "0000000287")

        credit_note = self._create_dgi_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
            move_type="out_refund",
            reversed_entry=contribuyente,
        )
        self.assertEqual(credit_note.name, "0000000288")
        credit_note.action_send_to_dgi()
        self._assert_hka_accepted(credit_note, "0000000288")

    def test_live_deduction_invoices_accepted_by_hka(self):
        """Send the down-payment remainder and a negative-discount invoice to HKA."""
        self.dgi_sequence.sudo().write({"number_next": 289})
        invoice_date = "2026-09-05"
        _sale, downpayment, final = self._create_sale_final_invoice_with_downpayment(
            partner=self.partner_live_contribuyente,
            downpayment_date=invoice_date,
            final_date=invoice_date,
        )
        self.assertEqual(downpayment.name, "0000000289")
        self.assertEqual(final.name, "0000000290")
        self._assert_hka_payload_deducts_negative_lines(final, 1000.0)

        downpayment.action_send_to_dgi()
        self._assert_hka_accepted(downpayment, "0000000289")
        final.action_send_to_dgi()
        self._assert_hka_accepted(final, "0000000290")

        discount = self._create_negative_discount_invoice(
            partner=self.partner_live_contribuyente,
            invoice_date=invoice_date,
        )
        self.assertEqual(discount.name, "0000000291")
        self._assert_hka_payload_deducts_negative_lines(discount, 1000.0)
        discount.action_send_to_dgi()
        self._assert_hka_accepted(discount, "0000000291")
