# -*- coding: utf-8 -*-

import base64
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon

LOST_CUFE = "B" * 66

HKA_ACCEPTED_LOST = {
    "codigo": "200",
    "resultado": "Procesado",
    "mensaje": "Autorizado",
    "cufe": LOST_CUFE,
    "qr": "QR-LOST",
    "fechaRecepcionDGI": "2026-03-15T12:00:00-05:00",
    "nroProtocoloAutorizacion": "PROT-LOST",
}

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
class TestL10nPaEdiReviewFixes(L10nPaEdiTestCommon):
    # ------------------------------------------------------------------
    # listaItems formula on unmerged lines
    # ------------------------------------------------------------------
    def _single_item_unmerged(self, **line_overrides):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[{**self._default_invoice_line_vals(), **line_overrides}],
            extra_vals={"hka_merge_same_dgi_code": False},
        )
        payload = self._assert_hka_payload_matches_move(invoice)
        items = payload["documento"]["listaItems"]
        self.assertEqual(len(items), 1)
        return invoice, items[0]

    def test_fractional_discount_falls_back_to_quantity_one(self):
        """3 x 10.00 at 33.33 %: 3 * (10.00 - 3.33) = 20.01 but the line is 20.00."""
        invoice, item = self._single_item_unmerged(
            quantity=3, price_unit=10.0, discount=33.33
        )
        self.assertAlmostEqual(invoice.amount_untaxed, 20.00)
        self.assertEqual(item["precioItem"], "20.00")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "20.00")
        self.assertNotIn("precioUnitarioDescuento", item)

    def test_exact_discount_keeps_quantity_and_discount(self):
        _invoice, item = self._single_item_unmerged(
            quantity=2, price_unit=10.0, discount=10.0
        )
        self.assertEqual(item["cantidad"], "2.00")
        self.assertEqual(item["precioUnitario"], "10.00")
        self.assertEqual(item["precioUnitarioDescuento"], "1.00")
        self.assertEqual(item["precioItem"], "18.00")

    def test_half_cent_quantity_product_falls_back_to_quantity_one(self):
        """2.5 x 3.33 = 8.325: Odoo books 8.33, a strict validator may not."""
        _invoice, item = self._single_item_unmerged(quantity=2.5, price_unit=3.33)
        self.assertEqual(item["precioItem"], "8.33")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "8.33")

    def test_merged_single_line_group_also_keeps_formula(self):
        """Merge on, but a lone line per DGI code still goes through the line path."""
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[{
                **self._default_invoice_line_vals(),
                "quantity": 3,
                "price_unit": 10.0,
                "discount": 33.33,
            }],
        )
        self.assertTrue(invoice.hka_merge_same_dgi_code)
        payload = self._assert_hka_payload_matches_move(invoice)
        item = payload["documento"]["listaItems"][0]
        self.assertEqual(item["cantidad"], "1.00")

    # ------------------------------------------------------------------
    # Contingency timestamp
    # ------------------------------------------------------------------
    def test_contingency_start_is_converted_to_panama_time(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.write({
            "hka_tipo_emision": "02",
            "hka_fecha_inicio_contingencia": "2026-09-05 12:00:00",  # UTC
            "hka_motivo_contingencia": "Sistema de facturacion fuera de linea",
        })
        payload = invoice._prepare_dgi_document_data()["documento"]["datosTransaccion"]
        self.assertEqual(payload["fechaInicioContingencia"], "2026-09-05T07:00:00-05:00")
        self.assertEqual(payload["fechaEmision"], "2026-03-15T00:00:00-05:00")

    # ------------------------------------------------------------------
    # Enviar receipts and HKA 102 recovery
    # ------------------------------------------------------------------
    def test_enviar_logs_detached_receipt_with_cufe(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        payload = invoice._prepare_dgi_document_data()
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api), "_make_request", return_value=(200, HKA_ACCEPTED_LOST)
        ):
            result = api.enviar(payload, move_id=invoice.id)

        self.assertTrue(result["success"])
        self.assertEqual(result["dgi_cufe"], LOST_CUFE)
        Log = self.env["hka.api.log"]
        key = Log._document_key_from_payload(payload)
        self.assertEqual(key, Log._document_key_from_move(invoice))
        receipt = Log._find_enviar_receipt(invoice.company_id, key)
        self.assertTrue(receipt)
        self.assertFalse(receipt.move_id)
        self.assertEqual(receipt.dgi_cufe, LOST_CUFE)
        self.assertEqual(receipt.document_number, invoice.name)
        self.assertIn(invoice.name, receipt.display_name)
        invoice.invalidate_recordset(["hka_api_log_count"])
        self.assertEqual(invoice.hka_api_log_count, 1)

    def _lost_receipt(self, invoice):
        """Simulate an Enviar whose transaction was rolled back after HKA said 200."""
        payload = invoice._prepare_dgi_document_data()
        Log = self.env["hka.api.log"]
        receipt_id = Log.log_api_call(
            api_method="enviar",
            request_data=payload,
            response_data=HKA_ACCEPTED_LOST,
            status="success",
            move_id=invoice.id,
            document_key=Log._document_key_from_payload(payload),
            dgi_cufe=LOST_CUFE,
        )
        self.assertTrue(receipt_id)
        self.assertFalse(invoice.dgi_cufe)
        return Log.browse(receipt_id)

    def test_duplicate_recovers_cufe_from_lost_receipt(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        receipt = self._lost_receipt(invoice)
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api), "_make_request", return_value=(200, HKA_DUPLICATE)
        ):
            invoice.action_process_edi_web_services(with_commit=False)

        self.assertTrue(invoice.dgi_sent)
        self.assertEqual(invoice.dgi_cufe, LOST_CUFE)
        self.assertEqual(invoice.dgi_qr, "QR-LOST")
        self.assertEqual(invoice.dgi_protocolo_autorizacion, "PROT-LOST")
        self.assertEqual(invoice.dgi_status, "procesado")
        self.assertEqual(invoice.edi_state, "sent")
        self.assertTrue(invoice.dgi_sent_date)
        logs = self.env["hka.api.log"].search(
            invoice._hka_api_log_domain(), order="id asc"
        )
        self.assertEqual(logs[:1], receipt)
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[1].status, "success")
        self.assertIn("#%s" % receipt.id, logs[1].error_message)

    def test_duplicate_without_receipt_stays_error(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api), "_make_request", return_value=(200, HKA_DUPLICATE)
        ):
            invoice.action_process_edi_web_services(with_commit=False)
        self.assertFalse(invoice.dgi_sent)
        self.assertFalse(invoice.dgi_cufe)
        self.assertFalse(invoice.dgi_sent_date)
        self.assertEqual(invoice.edi_state, "to_send")
        self.assertIn("102", invoice.dgi_error_message)

    def test_duplicate_with_different_total_is_not_recovered(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        receipt = self._lost_receipt(invoice)
        receipt.sudo().write({
            "request_data": receipt.request_data.replace(
                '"totalFactura": "1070.00"', '"totalFactura": "999.00"'
            )
        })
        self.assertIn('"totalFactura": "999.00"', receipt.request_data)
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api), "_make_request", return_value=(200, HKA_DUPLICATE)
        ):
            invoice.action_process_edi_web_services(with_commit=False)
        self.assertFalse(invoice.dgi_cufe)
        self.assertEqual(invoice.edi_state, "to_send")

    def test_duplicate_cufe_owned_by_other_invoice_is_not_recovered(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._lost_receipt(invoice)
        other = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(other, dgi_cufe=LOST_CUFE)
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api), "_make_request", return_value=(200, HKA_DUPLICATE)
        ):
            invoice.action_process_edi_web_services(with_commit=False)
        self.assertFalse(invoice.dgi_cufe)
        self.assertEqual(invoice.edi_state, "to_send")

    def test_anular_failure_keeps_its_log(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="A" * 66)
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api),
            "_make_request",
            return_value=(200, {"codigo": "400", "resultado": "Rechazado", "mensaje": "No"}),
        ):
            result = api.anular({"motivoAnulacion": "x" * 20}, move_id=invoice.id)
        self.assertFalse(result["success"])
        logs = self.env["hka.api.log"].search(invoice._hka_api_log_domain())
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs.api_method, "anular")
        self.assertEqual(logs.status, "error")
        self.assertFalse(logs.move_id)

    def test_backfill_document_keys_on_legacy_logs(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        legacy = self.env["hka.api.log"].log_api_call(
            api_method="enviar",
            request_data={"documento": {}},
            response_data=HKA_ACCEPTED_LOST,
            status="success",
            move_id=invoice.id,
            auto_commit=False,
        )
        legacy.sudo().write({"document_key": False, "document_number": False, "dgi_cufe": False})
        self.env["hka.api.log"]._backfill_document_keys()
        self.assertEqual(
            legacy.document_key,
            self.env["hka.api.log"]._document_key_from_move(invoice),
        )
        self.assertEqual(legacy.document_number, invoice.name)
        self.assertEqual(legacy.dgi_cufe, LOST_CUFE)

    # ------------------------------------------------------------------
    # Wizard / journal / reversal / config / hooks / downloads
    # ------------------------------------------------------------------
    def test_anulacion_wizard_short_reason_is_validation_error(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        with self.assertRaises(ValidationError):
            self.env["dgi.anulacion.wizard"].with_context(active_id=invoice.id).create({
                "motivo_anulacion": "too short",
            })

    def test_dgi_sequence_must_be_no_gap_ten_digits(self):
        bad = self.env["ir.sequence"].create({
            "name": "Bad DGI Sequence",
            "implementation": "standard",
            "prefix": "INV/",
            "padding": 5,
            "company_id": self.company.id,
        })
        with self.assertRaises(ValidationError) as error:
            self.sale_journal.write({"dgi_sequence_id": bad.id})
        message = str(error.exception)
        self.assertIn("No gap", message)
        self.assertIn("10 digits", message)
        self.assertIn("prefix", message)

    def test_reversal_wizard_gives_credit_note_type_04_not_manual(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="A" * 66)
        wizard = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"journal_id": invoice.journal_id.id, "reason": "Review fix"})
        action = wizard.reverse_moves()
        refund = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(refund.move_type, "out_refund")
        self.assertEqual(refund.reversed_entry_id, invoice)
        self.assertEqual(refund.hka_tipo_documento, "04")
        self.assertFalse(refund.hka_tipo_documento_manual)

    def test_duplicate_invoice_recomputes_document_type(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente, post=False)
        invoice.write({"hka_tipo_documento_manual": True, "hka_tipo_documento": "08"})
        copy = invoice.copy()
        self.assertFalse(copy.hka_tipo_documento_manual)
        self.assertEqual(copy.hka_tipo_documento, "01")

    def test_missing_api_url_gives_clear_error(self):
        self.company.hka_api_url = False
        api = self.env["l10n_pa_edi.hka_api"]
        with self.assertRaises(UserError) as error:
            api._make_request("api/Enviar", data={}, company=self.company)
        self.assertIn("HKA API URL", str(error.exception))
        self.assertFalse(self.env["res.company"].default_get(["hka_api_url"]).get("hka_api_url"))

    def test_auto_map_taxes_only_for_panama_companies(self):
        other = self.env["res.company"].create({
            "name": "US Co",
            "country_id": self.env.ref("base.us").id,
        })
        self.assertNotEqual(other.account_fiscal_country_id.code, "PA")
        group = self.env["account.tax.group"].with_company(other).create({
            "name": "US Taxes",
            "company_id": other.id,
        })
        foreign_tax = self.env["account.tax"].with_company(other).create({
            "name": "Sales 7%",
            "amount": 7.0,
            "type_tax_use": "sale",
            "company_id": other.id,
            "tax_group_id": group.id,
        })
        self.tax_itbms_7.hka_tax_code = False
        self.env["l10n_pa_edi.hka_api"]._auto_map_defaults()
        self.assertEqual(self.tax_itbms_7.hka_tax_code, "01")
        self.assertFalse(foreign_tax.hka_tax_code)

    def test_download_reuses_attachment(self):
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self._mark_dgi_sent(invoice, dgi_cufe="A" * 66)
        api = self.env["l10n_pa_edi.hka_api"]
        file_name = "%s.pdf" % invoice.name

        def descargar(*args, **kwargs):
            return {
                "success": True,
                "file_content": b"%PDF-1.4 " + str(descargar.calls).encode(),
                "file_name": file_name,
                "error_message": False,
            }

        descargar.calls = 0
        with patch.object(type(api), "descargar", side_effect=descargar):
            invoice.action_download_efactura()
            descargar.calls = 1
            action = invoice.action_download_efactura()

        attachments = self.env["ir.attachment"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", invoice.id),
            ("name", "=", file_name),
        ])
        self.assertEqual(len(attachments), 1)
        self.assertIn("/web/content/%s" % attachments.id, action["url"])
        self.assertEqual(base64.b64decode(attachments.datas), b"%PDF-1.4 1")
