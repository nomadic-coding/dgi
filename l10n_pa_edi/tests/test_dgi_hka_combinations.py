# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiHkaCombinations(L10nPaEdiTestCommon):
    """HKA Enviar field combinations that the UI and ORM must keep valid."""

    def test_invoice_defaults_to_internal_panama_sale(self):
        invoice = self._create_dgi_invoice(post=False)
        self.assertEqual(invoice.hka_tipo_documento, "01")
        self.assertEqual(invoice.hka_naturaleza_operacion, "01")
        self.assertEqual(invoice.hka_tipo_operacion, "1")
        self.assertEqual(invoice.hka_destino_operacion, "1")
        self.assertEqual(invoice.hka_tipo_venta, "1")
        self.assertEqual(invoice.hka_allowed_document_types, "01,08,09")
        self.assertEqual(invoice.hka_allowed_naturalezas, "01,10,12,13,14")

    def test_credit_note_uses_return_nature_and_hides_sale_type(self):
        invoice = self._create_dgi_invoice()
        credit = self._create_dgi_invoice(
            move_type="out_refund",
            reversed_entry=invoice,
        )
        self.assertEqual(credit.hka_tipo_documento, "04")
        self.assertEqual(credit.hka_naturaleza_operacion, "11")
        self.assertFalse(credit.hka_tipo_venta)
        self.assertFalse(credit.hka_is_sale_document)
        payload = credit._prepare_dgi_document_data()
        self.assertNotIn("tipoVenta", payload["documento"]["datosTransaccion"])
        self.assertEqual(
            payload["documento"]["datosTransaccion"]["naturalezaOperacion"],
            "11",
        )

    def test_invalid_document_type_snaps_back(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.hka_tipo_documento = "04"
        self.assertEqual(invoice.hka_tipo_documento, "01")

    def test_invalid_nature_snaps_to_first_allowed(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.hka_naturaleza_operacion = "21"
        self.assertEqual(invoice.hka_naturaleza_operacion, "01")

    def test_internal_bill_cannot_keep_foreign_destination(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.hka_destino_operacion = "2"
        self.assertEqual(invoice.hka_destino_operacion, "1")

    def test_foreign_partner_defaults_to_export_document(self):
        partner = self.env["res.partner"].create({
            "name": "US Buyer",
            "is_company": True,
            "country_id": self.env.ref("base.us").id,
            "vat": "US-12-3456789",
            "dgi_tipo_identificacion_extranjero": "02",
        })
        invoice = self._create_dgi_invoice(partner=partner, post=False)
        self.assertEqual(invoice.hka_tipo_documento, "03")
        self.assertEqual(invoice.hka_naturaleza_operacion, "02")
        self.assertEqual(invoice.hka_destino_operacion, "2")
        self.assertEqual(invoice.hka_tipo_operacion, "1")
        self.assertEqual(invoice.hka_allowed_document_types, "03,08,10")

    def test_cafe_no_generation_only_pairs_with_no_delivery(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.hka_formato_cafe = "2"
        self.assertEqual(invoice.hka_entrega_cafe, "2")
        invoice.hka_entrega_cafe = "1"
        self.assertEqual(invoice.hka_entrega_cafe, "2")
        invoice.hka_formato_cafe = "1"
        self.assertEqual(invoice.hka_entrega_cafe, "1")

    def test_contingency_emission_requires_reason(self):
        invoice = self._create_dgi_invoice(post=False)
        with self.assertRaises(ValidationError):
            invoice.write({
                "hka_tipo_emision": "02",
                "hka_fecha_inicio_contingencia": "2026-09-05 12:00:00",
                "hka_motivo_contingencia": "too short",
            })

    def test_contingency_payload_includes_hka_fields(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.write({
            "hka_tipo_emision": "02",
            "hka_fecha_inicio_contingencia": "2026-09-05 12:00:00",
            "hka_motivo_contingencia": "Sistema de facturacion fuera de linea",
        })
        payload = invoice._prepare_dgi_document_data()["documento"]["datosTransaccion"]
        self.assertEqual(payload["tipoEmision"], "02")
        self.assertTrue(payload["fechaInicioContingencia"])
        self.assertGreaterEqual(len(payload["motivoContingencia"]), 15)

    def test_other_payment_method_requires_description(self):
        invoice = self._create_dgi_invoice(post=False)
        with self.assertRaises(ValidationError):
            invoice.hka_forma_pago = "99"

    def test_other_payment_method_payload(self):
        invoice = self._create_dgi_invoice(post=False)
        invoice.write({
            "hka_forma_pago": "99",
            "hka_desc_forma_pago": "Pago mixto corporativo",
        })
        forma = invoice._prepare_dgi_document_data()["documento"]["totalesSubTotales"][
            "listaFormaPago"
        ][0]
        self.assertEqual(forma["formaPagoFact"], "99")
        self.assertEqual(forma["descFormaPago"], "Pago mixto corporativo")

    def test_panama_partner_rejects_foreign_ruc_type(self):
        with self.assertRaises(ValidationError):
            self.partner_contribuyente.dgi_tipo_ruc = "04"
