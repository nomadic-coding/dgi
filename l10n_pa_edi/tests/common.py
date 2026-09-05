# -*- coding: utf-8 -*-

import os

from lxml import etree

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tools import file_open


LIST_ITEM_TAGS = {
    "listaItems": "item",
    "listaFormaPago": "formaPago",
    "listaDocsFiscalReferenciados": "docFiscalReferenciado",
}


class L10nPaEdiTestCommon(AccountTestInvoicingCommon):
    """Shared Panama DGI / HKA fixtures. Does not call the real HKA API."""

    @classmethod
    @AccountTestInvoicingCommon.setup_country("pa")
    def setUpClass(cls):
        super().setUpClass()

        cls.country_pa = cls.env.ref("base.pa")
        cls.company = cls.company_data["company"]
        cls.currency = cls.company_data["currency"]

        cls._map_dgi_codes()
        cls._configure_hka_settings()
        cls._configure_dgi_journal()
        cls._configure_sale_tax()
        cls._create_partners()
        cls._create_products()

    @classmethod
    def _map_dgi_codes(cls):
        """Link official DGI catalog rows onto the records the payload reads."""
        Mapping = cls.env["dgi.code.mapping"]

        cls.dgi_uom_und = cls.env.ref("l10n_pa_dgi_code_mapping.dgi_mapping_504")
        cls.dgi_currency_pab = cls.env.ref("l10n_pa_dgi_code_mapping.dgi_mapping_690")
        cls.dgi_currency_usd = cls.env.ref("l10n_pa_dgi_code_mapping.dgi_mapping_728")
        cls.dgi_country_pa = cls.env.ref("l10n_pa_dgi_code_mapping.dgi_mapping_917")
        cls.dgi_product_code = cls.env.ref("l10n_pa_dgi_code_mapping.dgi_mapping_1")

        cls.country_pa.dgi_code_id = cls.dgi_country_pa
        cls.env.ref("base.USD").dgi_code_id = cls.dgi_currency_usd
        pab = cls.env.ref("base.PAB", raise_if_not_found=False)
        if pab:
            pab.dgi_code_id = cls.dgi_currency_pab
        if not cls.currency.dgi_code_id:
            currency_code = cls.currency.name
            mapping = Mapping.search(
                [("mapping_type", "=", "currency"), ("code", "=", currency_code)],
                limit=1,
            )
            if mapping:
                cls.currency.dgi_code_id = mapping

        cls.uom_unit.dgi_code_id = cls.dgi_uom_und

        cls.state_panama = cls.env.ref("l10n_pa_location.state_pa_8")
        cls.distrito_panama = cls.env.ref("l10n_pa_location.distrito_pa_8_8")
        cls.corregimiento_san_felipe = cls.env.ref("l10n_pa_location.corr_8_8_1")

    @classmethod
    def _configure_hka_settings(cls):
        cls.company.write({
            "hka_api_url": "https://hka.test.example",
            "hka_usuario": "test-user",
            "hka_clave": "test-password",
            "hka_timeout": 30,
            "hka_verify_ssl": True,
            "hka_merge_same_dgi_code": True,
        })

    @classmethod
    def _configure_dgi_journal(cls):
        cls.dgi_sequence = cls.env["ir.sequence"].create({
            "name": "DGI Test Sequence",
            "code": "l10n_pa_edi.dgi.test",
            "implementation": "no_gap",
            "prefix": "",
            "padding": 10,
            "number_next": 1,
            "number_increment": 1,
            "company_id": cls.company.id,
        })
        cls.sale_journal = cls.company_data["default_journal_sale"]
        cls.hka_edi_format = cls.env.ref("l10n_pa_edi.edi_format_pa_dgi_hka")
        cls.sale_journal.write({
            "use_dgi_electronic_invoicing": True,
            "dgi_codigo_sucursal_emisor": "0000",
            "dgi_punto_facturacion_fiscal": "001",
            "dgi_sequence_id": cls.dgi_sequence.id,
            "edi_format_ids": [Command.set(cls.hka_edi_format.ids)],
        })

    @classmethod
    def _configure_sale_tax(cls):
        cls.tax_itbms_7 = cls.company_data["default_tax_sale"]
        cls.tax_itbms_7.hka_tax_code = "01"

    @classmethod
    def _panama_address_vals(cls):
        return {
            "country_id": cls.country_pa.id,
            "state_id": cls.state_panama.id,
            "l10n_pa_distrito_id": cls.distrito_panama.id,
            "l10n_pa_corregimiento_id": cls.corregimiento_san_felipe.id,
            "street": "Calle 50",
            "street2": "Edificio Test",
            "phone": "+507 263-1234",
            "email": "acme@example.com",
        }

    @classmethod
    def _create_partners(cls):
        address = cls._panama_address_vals()
        Partner = cls.env["res.partner"]
        cls.partner_contribuyente = Partner.create({
            **address,
            "name": "Acme Panama SA",
            "is_company": True,
            "vat": "155701888-2-2019",
            "dgi_ruc": "155701888-2-2019",
            "dgi_tipo_ruc": "02",
            "dgi_dv": "15",
            "dgi_razon_social": "ACME PANAMA S.A.",
        })
        cls.partner_contribuyente._dgi_set_ruc_validated({
            "vat": "155701888-2-2019",
            "dgi_dv": "15",
            "dgi_razon_social": "ACME PANAMA S.A.",
        })
        cls.partner_consumidor_final = cls.env["res.partner"].create({
            **address,
            "name": "Juan Perez",
            "is_company": False,
            "email": "juan@example.com",
        })
        cls.partner_gobierno = Partner.create({
            **address,
            "name": "Ministerio de Economia",
            "is_company": True,
            "vat": "123456789-1-2020",
            "dgi_ruc": "123456789-1-2020",
            "dgi_tipo_ruc": "03",
            "dgi_dv": "08",
            "dgi_razon_social": "MINISTERIO DE ECONOMIA Y FINANZAS",
        })
        cls.partner_gobierno._dgi_set_ruc_validated({
            "vat": "123456789-1-2020",
            "dgi_dv": "08",
            "dgi_razon_social": "MINISTERIO DE ECONOMIA Y FINANZAS",
        })

    @classmethod
    def _create_products(cls):
        cls.product_service = cls._create_product(
            name="Consulting service",
            default_code="SVC-001",
            lst_price=1000.0,
            standard_price=800.0,
            uom_id=cls.uom_unit.id,
            taxes_id=[Command.set(cls.tax_itbms_7.ids)],
        )
        cls.product_service.product_tmpl_id.dgi_code_id = cls.dgi_product_code

    def setUp(self):
        super().setUp()
        self.dgi_sequence.sudo().write({"number_next": 1})

    @classmethod
    def _create_dgi_invoice(
        cls,
        partner=None,
        post=True,
        invoice_date="2026-03-15",
        move_type="out_invoice",
        reversed_entry=None,
        line_vals=None,
        extra_vals=None,
    ):
        partner = partner or cls.partner_contribuyente
        vals = {
            "move_type": move_type,
            "partner_id": partner.id,
            "invoice_date": invoice_date,
            "date": invoice_date,
            "journal_id": cls.sale_journal.id,
            "invoice_line_ids": [
                Command.create(line)
                for line in (line_vals or [cls._default_invoice_line_vals()])
            ],
        }
        if reversed_entry:
            vals["reversed_entry_id"] = reversed_entry.id
        if extra_vals:
            vals.update(extra_vals)
        invoice = cls.env["account.move"].create(vals)
        if post:
            invoice.action_post()
        return invoice

    def _mark_dgi_sent(self, move, **vals):
        payload = {
            "dgi_status": "procesado",
            "dgi_cufe": "TEST-CUFE-001",
        }
        payload.update(vals)
        payload.pop("dgi_sent", None)
        move._dgi_write_api_fields(payload)
        existing = move._l10n_pa_hka_edi_documents()
        if existing:
            existing.sudo().write({
                "state": "sent",
                "error": False,
                "blocking_level": False,
            })
        else:
            self.env["account.edi.document"].create({
                "move_id": move.id,
                "edi_format_id": self.hka_edi_format.id,
                "state": "sent",
            })
        return move

    @classmethod
    def _default_invoice_line_vals(cls):
        return {
            "product_id": cls.product_service.id,
            "name": "Consulting service",
            "quantity": 1,
            "price_unit": 1000.0,
            "tax_ids": [Command.set(cls.tax_itbms_7.ids)],
        }

    def _create_sale_final_invoice_with_downpayment(
        self,
        partner=None,
        downpayment_date="2026-03-10",
        final_date="2026-03-15",
        downpayment_percent=20.0,
    ):
        """Confirm a 1000 service SO, invoice a % down payment, then the deducted remainder."""
        partner = partner or self.partner_contribuyente
        self.product_service.invoice_policy = "order"
        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "journal_id": self.sale_journal.id,
            "order_line": [Command.create({
                "product_id": self.product_service.id,
                "name": "Consulting service",
                "product_uom_qty": 1,
                "price_unit": 1000.0,
            })],
        })
        sale_order.action_confirm()

        wizard_ctx = {
            "active_model": "sale.order",
            "active_id": sale_order.id,
            "active_ids": sale_order.ids,
        }
        self.env["sale.advance.payment.inv"].with_context(wizard_ctx).create({
            "advance_payment_method": "percentage",
            "amount": downpayment_percent,
        }).create_invoices()

        downpayment = sale_order.invoice_ids
        downpayment.invoice_date = downpayment_date
        downpayment.action_post()

        self.env["sale.advance.payment.inv"].with_context(wizard_ctx).create({
            "advance_payment_method": "delivered",
            "deduct_down_payments": True,
        }).create_invoices()

        final = sale_order.invoice_ids.filtered(lambda move: move.id != downpayment.id)
        final.invoice_date = final_date
        final.action_post()
        return sale_order, downpayment, final

    def _create_negative_discount_invoice(
        self, partner=None, invoice_date="2026-03-15", post=True
    ):
        """Invoice with a positive line and a negative commercial-discount line."""
        return self._create_dgi_invoice(
            partner=partner,
            post=post,
            invoice_date=invoice_date,
            line_vals=[
                self._default_invoice_line_vals(),
                {
                    "product_id": self.product_service.id,
                    "name": "Commercial discount",
                    "quantity": 1,
                    "price_unit": -100.0,
                    "tax_ids": [Command.set(self.tax_itbms_7.ids)],
                },
            ],
        )

    def _assert_hka_payload_deducts_negative_lines(self, move, gross_untaxed):
        payload = move._prepare_dgi_document_data()
        totales = payload["documento"]["totalesSubTotales"]
        items = payload["documento"]["listaItems"]
        self.assertLess(move.amount_untaxed, gross_untaxed)
        self.assertAlmostEqual(float(totales["totalPrecioNeto"]), move.amount_untaxed)
        self.assertAlmostEqual(float(totales["totalFactura"]), move.amount_total)
        self.assertAlmostEqual(
            sum(float(item["precioItem"]) for item in items),
            move.amount_untaxed,
        )
        self.assertAlmostEqual(
            sum(float(item["valorTotal"]) for item in items),
            move.amount_total,
        )
        for item in items:
            self.assertGreater(float(item["cantidad"]), 0)
            self.assertGreaterEqual(float(item["precioItem"]), 0)
            self._assert_hka_item_formula(item)
        return payload

    def _assert_hka_item_formula(self, item):
        """HKA: precioItem = cantidad * (precioUnitario - precioUnitarioDescuento)."""
        qty = float(item["cantidad"])
        unit = float(item["precioUnitario"])
        discount = float(item.get("precioUnitarioDescuento") or 0.0)
        precio = float(item["precioItem"])
        self.assertAlmostEqual(qty * (unit - discount), precio, places=2)
        self.assertAlmostEqual(
            float(item["valorTotal"]),
            precio
            + float(item.get("valorITBMS") or 0.0)
            + float(item.get("valorISC") or 0.0),
            places=2,
        )
        tasa = item.get("tasaITBMS") or "00"
        rate = {"00": 0.0, "01": 0.07, "02": 0.10, "03": 0.15}.get(tasa, 0.0)
        self.assertAlmostEqual(
            float(item.get("valorITBMS") or 0.0),
            round(precio * rate, 2),
            places=2,
        )

    def _assert_hka_payload_matches_move(self, move, payload=None):
        payload = payload or move._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        totales = payload["documento"]["totalesSubTotales"]
        self.assertTrue(items)
        self.assertEqual(totales["nroItems"], str(len(items)))
        self.assertAlmostEqual(float(totales["totalPrecioNeto"]), move.amount_untaxed)
        self.assertAlmostEqual(
            sum(float(item["precioItem"]) for item in items),
            move.amount_untaxed,
        )
        self.assertAlmostEqual(
            sum(float(item["valorITBMS"]) for item in items),
            float(totales["totalITBMS"]),
        )
        self.assertAlmostEqual(
            sum(float(item["valorTotal"]) for item in items),
            float(totales["totalFactura"]),
        )
        for item in items:
            self._assert_hka_item_formula(item)
        return payload

    def documento_to_xml_tree(self, payload):
        """Turn the HKA Enviar JSON payload into XML for assertXmlTreeEqual."""
        root = etree.Element("enviar")
        self._value_to_xml(root, "documento", payload["documento"])
        return root

    def _value_to_xml(self, parent, key, value):
        if isinstance(value, dict):
            node = etree.SubElement(parent, key)
            for child_key, child_value in value.items():
                self._value_to_xml(node, child_key, child_value)
            return
        if isinstance(value, list):
            node = etree.SubElement(parent, key)
            item_tag = LIST_ITEM_TAGS.get(key, "item")
            for item in value:
                if isinstance(item, dict):
                    item_node = etree.SubElement(node, item_tag)
                    for child_key, child_value in item.items():
                        self._value_to_xml(item_node, child_key, child_value)
                else:
                    item_node = etree.SubElement(node, item_tag)
                    item_node.text = "" if item is False or item is None else str(item)
            return
        node = etree.SubElement(parent, key)
        node.text = "" if value is False or value is None else str(value)

    def _assert_documento_xml_equal(self, move, fixture_filename):
        payload = move._prepare_dgi_document_data()
        generated = self.documento_to_xml_tree(payload)
        fixture_path = f"l10n_pa_edi/tests/files/{fixture_filename}"
        if os.environ.get("GENERATE_DGI_FIXTURES"):
            xml = etree.tostring(
                generated, pretty_print=True, encoding="unicode", xml_declaration=False,
            )
            absolute = file_open(fixture_path, "rb").name
            with open(absolute, "w", encoding="utf-8") as fixture:
                fixture.write(xml)
        with file_open(fixture_path, "rb") as fixture:
            expected = self.get_xml_tree_from_string(fixture.read())
        self.assertXmlTreeEqual(generated, expected)
