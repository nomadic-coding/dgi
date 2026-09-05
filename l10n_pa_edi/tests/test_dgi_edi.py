# -*- coding: utf-8 -*-

import importlib.util
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.addons.l10n_pa_edi.hooks import (
    HKA_UPGRADE_QUEUE_ERROR,
    _backfill_hka_edi_documents,
    _drop_legacy_dgi_auto_send_column,
    _enable_hka_edi_on_dgi_journals,
)
from odoo.modules.module import get_module_path
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiFormat(L10nPaEdiTestCommon):
    def test_format_applies_to_dgi_sale_invoices(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        applicability = self.hka_edi_format._get_move_applicability(invoice)
        self.assertTrue(applicability)
        self.assertIn("post", applicability)
        self.assertIn("cancel", applicability)

    def test_format_skips_journals_without_dgi(self):
        self.sale_journal.use_dgi_electronic_invoicing = False
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            extra_vals={"journal_id": self.sale_journal.id},
        )
        self.assertFalse(self.hka_edi_format._get_move_applicability(invoice))

    def test_check_move_configuration_does_not_block_post(self):
        errors = self.hka_edi_format._check_move_configuration(
            self._create_dgi_invoice(partner=self.partner_contribuyente, post=False)
        )
        self.assertFalse(errors)

    def test_cancel_without_motivo_returns_error(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="TEST-CUFE-NO-MOTIVO")
        result = self.hka_edi_format._l10n_pa_edi_cancel_invoice(invoice)
        self.assertFalse(result[invoice].get("success"))
        self.assertIn("cancellation reason", result[invoice]["error"].lower())
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.dgi_status, "procesado")

    def test_button_cancel_posted_moves_opens_wizard(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="TEST-CUFE-EDI-CANCEL")
        action = invoice.button_cancel_posted_moves()
        self.assertEqual(action["res_model"], "dgi.anulacion.wizard")
        self.assertEqual(action["context"]["active_id"], invoice.id)


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiUpgrade(L10nPaEdiTestCommon):
    def _load_end_migrate(self):
        path = Path(get_module_path("l10n_pa_edi")) / "migrations" / "18.0.1.1.0" / "end-migrate.py"
        spec = importlib.util.spec_from_file_location("l10n_pa_edi_end_migrate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_backfill_sent_invoice_creates_sent_document(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="OLD-CUFE-SENT")
        invoice.edi_document_ids.unlink()

        _backfill_hka_edi_documents(self.env)

        doc = invoice._l10n_pa_hka_edi_documents()
        self.assertEqual(len(doc), 1)
        self.assertEqual(doc.state, "sent")
        self.assertTrue(invoice.dgi_sent)

    def test_backfill_anulado_invoice_creates_cancelled_document(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="OLD-CUFE-ANULADO")
        invoice._dgi_write_api_fields({"dgi_status": "anulado"})
        invoice.edi_document_ids.unlink()

        _backfill_hka_edi_documents(self.env)

        doc = invoice._l10n_pa_hka_edi_documents()
        self.assertEqual(doc.state, "cancelled")
        self.assertTrue(invoice.dgi_sent)

    def test_backfill_unsent_invoice_queues_without_calling_hka(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice.edi_document_ids.unlink()

        _backfill_hka_edi_documents(self.env)

        doc = invoice._l10n_pa_hka_edi_documents()
        self.assertEqual(doc.state, "to_send")
        self.assertEqual(doc.blocking_level, "error")
        self.assertIn(HKA_UPGRADE_QUEUE_ERROR, doc.error or "")

        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "enviar",
        ) as enviar:
            invoice.action_process_edi_web_services(with_commit=False)
        enviar.assert_not_called()
        self.assertFalse(invoice.dgi_cufe)

    def test_retry_sends_upgrade_queued_invoice(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        invoice.edi_document_ids.unlink()
        _backfill_hka_edi_documents(self.env)

        result = {
            "success": True,
            "status": "procesado",
            "error_message": False,
            "dgi_cufe": "CUFE-AFTER-UPGRADE",
            "dgi_qr": "QR",
            "dgi_fecha_recepcion": "2026-03-15T12:00:00-05:00",
            "dgi_protocolo_autorizacion": "PROT",
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
            invoice.action_retry_edi_documents_error()

        self.assertEqual(invoice.dgi_cufe, "CUFE-AFTER-UPGRADE")
        self.assertEqual(invoice.edi_state, "sent")

    def test_enable_format_on_existing_dgi_journal(self):
        self.env["account.edi.document"].search([
            ("move_id.journal_id", "=", self.sale_journal.id),
            ("edi_format_id", "=", self.hka_edi_format.id),
        ]).unlink()
        self.sale_journal.write({
            "edi_format_ids": [Command.unlink(self.hka_edi_format.id)],
        })
        self.assertNotIn(self.hka_edi_format, self.sale_journal.edi_format_ids)

        _enable_hka_edi_on_dgi_journals(self.env)
        self.assertIn(self.hka_edi_format, self.sale_journal.edi_format_ids)

    def test_backfill_is_idempotent(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="OLD-CUFE-ONCE")
        invoice.edi_document_ids.unlink()
        _backfill_hka_edi_documents(self.env)
        _backfill_hka_edi_documents(self.env)
        self.assertEqual(len(invoice._l10n_pa_hka_edi_documents()), 1)

    def test_drop_legacy_auto_send_column(self):
        self.env.cr.execute(
            "ALTER TABLE account_journal ADD COLUMN IF NOT EXISTS dgi_auto_send_on_post boolean"
        )
        _drop_legacy_dgi_auto_send_column(self.env.cr)
        self.env.cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'account_journal'
              AND column_name = 'dgi_auto_send_on_post'
            """
        )
        self.assertFalse(self.env.cr.fetchone())

    def test_end_migrate_script_runs(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="MIGRATE-SCRIPT-CUFE")
        invoice.edi_document_ids.unlink()

        self._load_end_migrate().migrate(self.env.cr, "18.0.1.0.0")
        invoice.invalidate_recordset()

        doc = invoice._l10n_pa_hka_edi_documents()
        self.assertEqual(doc.state, "sent")
        self.assertIn(self.hka_edi_format, self.sale_journal.edi_format_ids)
