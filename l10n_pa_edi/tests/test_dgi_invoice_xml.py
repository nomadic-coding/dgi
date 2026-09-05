# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiInvoiceXml(L10nPaEdiTestCommon):
    """Build real DGI invoices and lock the HKA Enviar payload as XML fixtures."""

    def test_contribuyente_invoice_matches_xml(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)

        self.assertEqual(invoice.state, "posted")
        self.assertTrue(invoice.name)
        self.assertNotEqual(invoice.name, "/")
        self.assertEqual(invoice.hka_tipo_documento, "01")
        self.assertEqual(invoice.partner_id.dgi_tipo_cliente_fe, "01")
        self.assertEqual(invoice.amount_untaxed, 1000.0)
        self.assertEqual(invoice.amount_total, 1070.0)

        self._assert_documento_xml_equal(invoice, "invoice_contribuyente.xml")

    def test_consumidor_final_invoice_matches_xml(self):
        invoice = self._create_dgi_invoice(partner=self.partner_consumidor_final)

        self.assertEqual(invoice.partner_id.dgi_tipo_cliente_fe, "02")
        self._assert_documento_xml_equal(invoice, "invoice_consumidor_final.xml")

    def test_credit_note_matches_xml(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice.write({
            "dgi_sent": True,
            "dgi_status": "procesado",
            "dgi_cufe": "TEST-CUFE-001",
        })

        credit_note = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            invoice_date="2026-03-20",
            move_type="out_refund",
            reversed_entry=invoice,
        )

        self.assertEqual(credit_note.hka_tipo_documento, "04")
        self.assertTrue(credit_note.name)
        self.assertNotEqual(credit_note.name, "/")
        self.assertNotEqual(credit_note.name, invoice.name)
        self._assert_documento_xml_equal(credit_note, "credit_note_contribuyente.xml")

    def test_send_to_dgi_writes_response_fields(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        result = {
            "success": True,
            "status": "procesado",
            "error_message": False,
            "dgi_cufe": "CUFE-FROM-HKA",
            "dgi_qr": "QR-DATA",
            "dgi_fecha_recepcion": "2026-03-15T12:00:00-05:00",
            "dgi_protocolo_autorizacion": "PROT-1",
            "codigo": "200",
            "mensaje": "OK",
        }

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=result,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_send_to_dgi()

        self.assertTrue(invoice.dgi_sent)
        self.assertEqual(invoice.dgi_status, "procesado")
        self.assertEqual(invoice.dgi_cufe, "CUFE-FROM-HKA")
        self.assertEqual(invoice.dgi_qr, "QR-DATA")

    def test_send_to_dgi_rejected_does_not_mark_sent(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        result = {
            "success": False,
            "status": "rechazado",
            "error_message": "Code: 400, Message: Invalid RUC",
            "dgi_cufe": False,
            "dgi_qr": False,
            "dgi_fecha_recepcion": False,
            "dgi_protocolo_autorizacion": False,
            "codigo": "400",
            "mensaje": "Invalid RUC",
        }

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=result,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_send_to_dgi()

        self.assertFalse(invoice.dgi_sent)
        self.assertEqual(invoice.dgi_status, "rechazado")
        self.assertIn("Invalid RUC", invoice.dgi_error_message)

    def test_cannot_send_draft_invoice(self):
        invoice = self._create_dgi_invoice(post=False)

        with self.assertRaises(UserError):
            invoice.action_send_to_dgi()

    def test_cannot_send_twice(self):
        invoice = self._create_dgi_invoice()
        invoice.write({
            "dgi_sent": True,
            "dgi_status": "procesado",
            "dgi_cufe": "ALREADY-SENT",
        })

        with self.assertRaises(UserError):
            invoice.action_send_to_dgi()
