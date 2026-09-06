# -*- coding: utf-8 -*-

from unittest.mock import patch

import requests
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon

HKA_DUPLICATE = {
    "codigo": "102",
    "resultado": "error",
    "mensaje": "El documento está duplicado",
    "cufe": "FE-DUPLICATE-CUFE",
    "qr": "QR-DUP",
    "fechaRecepcionDGI": "2026-09-06T05:01:40",
    "nroProtocoloAutorizacion": "PROT-DUP",
}


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
        self.assertFalse(
            invoice.edi_document_ids.attachment_id,
            "HKA JSON must not become the EDI mail attachment",
        )
        extras = self.env["account.move.send"]._get_invoice_extra_attachments(invoice)
        self.assertFalse(
            extras.filtered(lambda att: (att.name or "").endswith("_hka.json"))
        )

    def test_existing_hka_json_is_not_mailed(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="CUFE-MAIL")
        attachment = self.env["ir.attachment"].create({
            "name": "%s_hka.json" % invoice.name,
            "raw": b'{"documento": {}}',
            "mimetype": "application/json",
            "res_model": invoice._name,
            "res_id": invoice.id,
        })
        invoice._l10n_pa_hka_edi_documents().sudo().attachment_id = attachment
        extras = self.env["account.move.send"]._get_invoice_extra_attachments(invoice)
        self.assertNotIn(attachment, extras)
        self.assertEqual(
            invoice._l10n_pa_hka_edi_documents()._filter_edi_attachments_for_mailing(),
            {},
        )

    def test_duplicate_enviar_with_cufe_marks_invoice_sent(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        parsed = self.env["l10n_pa_edi.hka_api"]._parse_enviar_response(HKA_DUPLICATE)
        self.assertTrue(parsed["success"])
        self.assertEqual(parsed["dgi_cufe"], "FE-DUPLICATE-CUFE")
        self.assertEqual(parsed["status"], "procesado")

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=parsed,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_process_edi_web_services(with_commit=False)

        self.assertEqual(invoice.edi_state, "sent")
        self.assertEqual(invoice.dgi_cufe, "FE-DUPLICATE-CUFE")
        self.assertTrue(invoice.dgi_sent)

    def test_duplicate_enviar_belongs_to_same_move_retry(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        api = self.env["l10n_pa_edi.hka_api"]
        parsed = api._parse_enviar_response(HKA_DUPLICATE, move=invoice)
        self.assertTrue(parsed["success"])

        self._mark_dgi_sent(invoice, dgi_cufe="FE-DUPLICATE-CUFE")
        parsed_again = api._parse_enviar_response(HKA_DUPLICATE, move=invoice)
        self.assertTrue(parsed_again["success"])

    def test_duplicate_enviar_rejected_when_another_invoice_owns_cufe(self):
        owner = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(owner, dgi_cufe="FE-DUPLICATE-CUFE")
        other = self._create_dgi_invoice(partner=self.partner_contribuyente)
        parsed = self.env["l10n_pa_edi.hka_api"]._parse_enviar_response(
            HKA_DUPLICATE, move=other
        )
        self.assertFalse(parsed["success"])
        self.assertIn("already belongs", parsed["error_message"])

    def test_rejected_enviar_with_cufe_does_not_mark_sent_and_can_retry(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        rejected = {
            "success": False,
            "status": "rechazado",
            "error_message": "Code: 201, Message: Schema error",
            "dgi_cufe": "SHOULD-NOT-STORE",
            "dgi_qr": "QR-REJECT",
            "dgi_fecha_recepcion": "2026-09-06T05:01:40",
            "dgi_protocolo_autorizacion": "PROT-REJECT",
            "codigo": "201",
            "mensaje": "Schema error",
        }
        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=rejected,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_process_edi_web_services(with_commit=False)

        self.assertFalse(invoice.dgi_sent)
        self.assertFalse(invoice.dgi_cufe)
        self.assertEqual(invoice.dgi_status, "rechazado")
        self.assertEqual(invoice.edi_state, "to_send")

        success = {
            "success": True,
            "status": "procesado",
            "error_message": False,
            "dgi_cufe": "CUFE-RETRY",
            "dgi_qr": "QR-RETRY",
            "dgi_fecha_recepcion": "2026-09-06T05:02:00",
            "dgi_protocolo_autorizacion": "PROT-RETRY",
            "codigo": "200",
            "mensaje": "OK",
        }
        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=success,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_retry_edi_documents_error()

        self.assertTrue(invoice.dgi_sent)
        self.assertEqual(invoice.dgi_cufe, "CUFE-RETRY")
        self.assertEqual(invoice.edi_state, "sent")

    def test_make_request_refreshes_token_once_on_401(self):
        api = self.env["l10n_pa_edi.hka_api"]
        ok = type("Resp", (), {})()
        ok.status_code = 200
        ok.content = b'{"ok": true}'
        ok.json = lambda: {"ok": True}
        ok.raise_for_status = lambda: None
        unauthorized = type("Resp", (), {})()
        unauthorized.status_code = 401
        unauthorized.content = b""
        unauthorized.raise_for_status = lambda: (_ for _ in ()).throw(
            requests.exceptions.HTTPError("401")
        )

        with patch.object(
            type(api), "_get_access_token", return_value="stale-token"
        ), patch.object(type(api), "_clear_access_token") as clear_token, patch.object(
            type(api),
            "_http_request",
            side_effect=[unauthorized, ok],
        ) as http_request:
            status, payload = api._make_request("api/Enviar", data={"documento": {}})

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(http_request.call_count, 2)
        clear_token.assert_called_once()

    def test_cufe_alone_does_not_mark_invoice_sent(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice._dgi_write_api_fields({"dgi_cufe": "CUFE-WITHOUT-STATUS"})
        self.assertEqual(invoice.dgi_cufe, "CUFE-WITHOUT-STATUS")
        self.assertFalse(invoice.dgi_sent)
        self.assertEqual(invoice.edi_state, "to_send")

    def test_procesado_without_cufe_does_not_mark_sent(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice._dgi_write_api_fields({"dgi_status": "procesado"})
        self.assertEqual(invoice.dgi_status, "procesado")
        self.assertFalse(invoice.dgi_cufe)
        self.assertFalse(invoice.dgi_sent)

    def test_enviar_200_without_cufe_is_not_success(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        parsed = self.env["l10n_pa_edi.hka_api"]._parse_enviar_response(
            {
                "codigo": "200",
                "resultado": "procesado",
                "mensaje": "OK",
            },
            move=invoice,
        )
        self.assertFalse(parsed["success"])
        self.assertFalse(parsed["dgi_cufe"])
        self.assertIn("CUFE", parsed["error_message"])

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=parsed,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_process_edi_web_services(with_commit=False)

        self.assertFalse(invoice.dgi_sent)
        self.assertFalse(invoice.dgi_cufe)
        self.assertNotEqual(invoice.dgi_status, "procesado")
        self.assertEqual(invoice.edi_state, "to_send")

        success = {
            "success": True,
            "status": "procesado",
            "error_message": False,
            "dgi_cufe": "CUFE-AFTER-EMPTY-200",
            "dgi_qr": "QR-RETRY",
            "dgi_fecha_recepcion": "2026-09-06T05:02:00",
            "dgi_protocolo_autorizacion": "PROT-RETRY",
            "codigo": "200",
            "mensaje": "OK",
        }
        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
            return_value=success,
        ), patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            invoice.action_retry_edi_documents_error()

        self.assertTrue(invoice.dgi_sent)
        self.assertEqual(invoice.dgi_cufe, "CUFE-AFTER-EMPTY-200")
        self.assertEqual(invoice.edi_state, "sent")

    def test_commit_api_fields_keeps_cufe_on_current_record(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice._dgi_commit_api_fields({
            "dgi_status": "procesado",
            "dgi_cufe": "CUFE-COMMIT-ORDER",
            "dgi_error_message": False,
        })
        self.assertEqual(invoice.dgi_cufe, "CUFE-COMMIT-ORDER")
        self.assertEqual(invoice.dgi_status, "procesado")
