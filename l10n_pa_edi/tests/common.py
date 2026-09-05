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
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_pa_edi.hka_api_url", "https://hka.test.example")
        ICP.set_param("l10n_pa_edi.hka_usuario", "test-user")
        ICP.set_param("l10n_pa_edi.hka_clave", "test-password")
        ICP.set_param("l10n_pa_edi.hka_timeout", "30")
        ICP.set_param("l10n_pa_edi.hka_verify_ssl", "True")

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
        cls.sale_journal.write({
            "use_dgi_electronic_invoicing": True,
            "dgi_auto_send_on_post": False,
            "dgi_codigo_sucursal_emisor": "0000",
            "dgi_punto_facturacion_fiscal": "001",
            "dgi_sequence_id": cls.dgi_sequence.id,
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
        Partner = cls.env["res.partner"].with_context(dgi_ruc_validation=True)
        cls.partner_contribuyente = Partner.create({
            **address,
            "name": "Acme Panama SA",
            "is_company": True,
            "vat": "155701888-2-2019",
            "dgi_ruc": "155701888-2-2019",
            "dgi_tipo_ruc": "02",
            "dgi_dv": "15",
            "dgi_razon_social": "ACME PANAMA S.A.",
            "dgi_ruc_validated": True,
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
            "dgi_ruc_validated": True,
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

    @classmethod
    def _default_invoice_line_vals(cls):
        return {
            "product_id": cls.product_service.id,
            "name": "Consulting service",
            "quantity": 1,
            "price_unit": 1000.0,
            "tax_ids": [Command.set(cls.tax_itbms_7.ids)],
        }

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
