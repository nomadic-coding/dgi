# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo import Command
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
        self._mark_dgi_sent(invoice, dgi_cufe="TEST-CUFE-001")

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

    def test_credit_payment_sets_tiempo_pago(self):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            extra_vals={"hka_forma_pago": "01"},
        )
        payload = invoice._prepare_dgi_document_data()
        self.assertEqual(payload["documento"]["totalesSubTotales"]["tiempoPago"], "2")
        self.assertEqual(
            payload["documento"]["totalesSubTotales"]["listaFormaPago"][0]["formaPagoFact"],
            "01",
        )

    def test_sale_downpayment_is_deducted_in_hka_payload(self):
        """Final invoice after a down payment must send the net remainder, not the gross sale."""
        sale_order, downpayment, final = self._create_sale_final_invoice_with_downpayment()
        deduction_lines = final.invoice_line_ids.filtered(
            lambda line: line.display_type == "product" and line.is_downpayment
        )
        self.assertTrue(deduction_lines)
        self.assertTrue(
            any(
                line.quantity < 0 or line.price_subtotal < 0
                for line in deduction_lines
            ),
            "The final invoice must carry a negative down-payment deduction line",
        )
        self.assertAlmostEqual(
            final.amount_untaxed,
            sale_order.amount_untaxed - downpayment.amount_untaxed,
        )
        self.assertAlmostEqual(
            final.amount_total,
            sale_order.amount_total - downpayment.amount_total,
        )
        self._assert_hka_payload_deducts_negative_lines(final, sale_order.amount_untaxed)
        self._assert_documento_xml_equal(final, "invoice_downpayment_deduction.xml")

    def test_negative_discount_line_is_deducted_in_hka_payload(self):
        """A negative commercial-discount line must reduce the HKA totals, not be dropped."""
        invoice = self._create_negative_discount_invoice()
        discount_lines = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product" and line.price_subtotal < 0
        )
        self.assertTrue(discount_lines)
        self.assertAlmostEqual(invoice.amount_untaxed, 900.0)
        self.assertAlmostEqual(invoice.amount_total, 963.0)
        self._assert_hka_payload_deducts_negative_lines(invoice, 1000.0)
        self._assert_documento_xml_equal(invoice, "invoice_negative_discount.xml")

    def test_same_dgi_code_lines_are_merged(self):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[
                {
                    **self._default_invoice_line_vals(),
                    "name": "Consulting A",
                    "quantity": 2,
                    "price_unit": 1000.0,
                },
                {
                    **self._default_invoice_line_vals(),
                    "name": "Consulting B",
                    "quantity": 3,
                    "price_unit": 1000.0,
                },
            ],
        )
        self.assertTrue(invoice.hka_merge_same_dgi_code)
        self.assertAlmostEqual(invoice.amount_untaxed, 5000.0)
        self.assertAlmostEqual(invoice.amount_total, 5350.0)
        self._assert_documento_xml_equal(invoice, "invoice_merged_same_dgi_code.xml")

    def test_ten_same_dgi_code_lines_become_one_item(self):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[
                {
                    **self._default_invoice_line_vals(),
                    "name": "Consulting %s" % index,
                    "quantity": 1,
                    "price_unit": 100.0,
                }
                for index in range(10)
            ],
        )
        payload = invoice._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["cantidad"], "10.00")
        self.assertEqual(items[0]["precioItem"], "1000.00")
        self.assertEqual(items[0]["valorITBMS"], "70.00")
        self.assertEqual(items[0]["valorTotal"], "1070.00")
        self.assertEqual(payload["documento"]["totalesSubTotales"]["nroItems"], "1")

    def test_different_dgi_codes_are_not_merged(self):
        other = self._create_product(
            name="Pet supplies",
            default_code="PET-001",
            lst_price=500.0,
            standard_price=400.0,
            uom_id=self.uom_unit.id,
            taxes_id=[Command.set(self.tax_itbms_7.ids)],
        )
        other.product_tmpl_id.dgi_code_id = self.env.ref(
            "l10n_pa_dgi_code_mapping.dgi_mapping_2"
        )
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[
                self._default_invoice_line_vals(),
                {
                    "product_id": other.id,
                    "name": "Pet supplies",
                    "quantity": 1,
                    "price_unit": 500.0,
                    "tax_ids": [Command.set(self.tax_itbms_7.ids)],
                },
            ],
        )
        payload = invoice._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        self.assertEqual(len(items), 2)
        self.assertEqual(
            {item["codigo"] for item in items},
            {"SVC-001", "PET-001"},
        )

    def test_invoice_override_disables_merge(self):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            extra_vals={"hka_merge_same_dgi_code": False},
            line_vals=[
                {
                    **self._default_invoice_line_vals(),
                    "name": "Consulting A",
                },
                {
                    **self._default_invoice_line_vals(),
                    "name": "Consulting B",
                },
            ],
        )
        self.assertFalse(invoice.hka_merge_same_dgi_code)
        payload = invoice._prepare_dgi_document_data()
        self.assertEqual(len(payload["documento"]["listaItems"]), 2)

    def test_new_invoice_inherits_company_merge_default(self):
        self.company.hka_merge_same_dgi_code = False
        invoice = self._create_dgi_invoice(post=False)
        self.assertFalse(invoice.hka_merge_same_dgi_code)
        self.company.hka_merge_same_dgi_code = True
        invoice_on = self._create_dgi_invoice(post=False)
        self.assertTrue(invoice_on.hka_merge_same_dgi_code)

    def test_cannot_forge_dgi_sent_fields(self):
        invoice = self._create_dgi_invoice()
        invoice.write({
            "dgi_sent": True,
            "dgi_status": "procesado",
            "dgi_cufe": "FORGED",
        })
        self.assertFalse(invoice.dgi_sent)
        self.assertFalse(invoice.dgi_cufe)

    def test_merged_unit_times_qty_equals_precio_item(self):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[
                {**self._default_invoice_line_vals(), "quantity": 1, "price_unit": 10.00},
                {**self._default_invoice_line_vals(), "quantity": 1, "price_unit": 10.00},
                {**self._default_invoice_line_vals(), "quantity": 1, "price_unit": 10.01},
            ],
        )
        item = invoice._prepare_dgi_document_data()["documento"]["listaItems"][0]
        qty = float(item["cantidad"])
        unit = float(item["precioUnitario"])
        self.assertAlmostEqual(qty * unit, float(item["precioItem"]), places=2)

    def test_cannot_send_twice(self):
        invoice = self._create_dgi_invoice()
        self._mark_dgi_sent(invoice, dgi_cufe="ALREADY-SENT")

        with self.assertRaises(UserError):
            invoice.action_send_to_dgi()
