# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiAnulacion(L10nPaEdiTestCommon):
    def _sent_invoice(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice.write({
            "dgi_sent": True,
            "dgi_status": "procesado",
            "dgi_cufe": "TEST-CUFE-ANULAR",
        })
        return invoice

    def _wizard(self, invoice):
        return self.env["dgi.anulacion.wizard"].with_context(active_id=invoice.id).create({
            "motivo_anulacion": "Error en los datos de la factura enviada",
        })

    def test_anular_calls_hka_before_odoo_cancel(self):
        invoice = self._sent_invoice()
        wizard = self._wizard(invoice)
        order = []

        def anular(*args, **kwargs):
            order.append("hka")
            self.assertEqual(invoice.state, "posted")
            return {
                "success": True,
                "status": "Anulado",
                "error_message": False,
                "codigo": "200",
                "mensaje": "OK",
            }

        def button_cancel(*args, **kwargs):
            order.append("odoo")
            return True

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "anular",
            side_effect=anular,
        ), patch.object(
            type(invoice),
            "button_cancel",
            side_effect=button_cancel,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            wizard.action_anular()

        self.assertEqual(order, ["hka", "odoo"])
        self.assertEqual(invoice.dgi_status, "anulado")

    def test_anular_hka_failure_leaves_invoice_posted(self):
        invoice = self._sent_invoice()
        wizard = self._wizard(invoice)

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "anular",
            return_value={
                "success": False,
                "status": "Error: 400",
                "error_message": "Code: 400, Message: Already processed",
                "codigo": "400",
                "mensaje": "Already processed",
            },
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            with self.assertRaises(UserError) as error:
                wizard.action_anular()

        self.assertIn("was not canceled in Odoo", str(error.exception))
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.dgi_status, "procesado")
