# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiAutoSend(L10nPaEdiTestCommon):
    def test_post_does_not_call_hka_in_the_same_transaction(self):
        """Posting queues an EDI document; Enviar waits for Process now / cron."""
        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
        ) as enviar:
            invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)

        self.assertEqual(invoice.state, "posted")
        self.assertFalse(invoice.dgi_sent)
        self.assertEqual(invoice.edi_state, "to_send")
        enviar.assert_not_called()

    def test_process_edi_writes_response_after_post(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        result = {
            "success": True,
            "status": "procesado",
            "error_message": False,
            "dgi_cufe": "CUFE-AUTO",
            "dgi_qr": "QR-AUTO",
            "dgi_fecha_recepcion": "2026-03-15T12:00:00-05:00",
            "dgi_protocolo_autorizacion": "PROT-AUTO",
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
            invoice.action_process_edi_web_services(with_commit=False)

        self.assertTrue(invoice.dgi_sent)
        self.assertEqual(invoice.dgi_cufe, "CUFE-AUTO")
        self.assertEqual(invoice.edi_state, "sent")
