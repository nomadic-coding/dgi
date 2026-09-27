# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiGovernmentCpbs(L10nPaEdiTestCommon):
    def test_government_invoice_includes_cpbs(self):
        invoice = self._create_dgi_invoice(partner=self.partner_gobierno)
        payload = invoice._prepare_dgi_document_data()
        item = payload["documento"]["listaItems"][0]
        self.assertEqual(item["codigoCPBS"], self.dgi_product_code.code)
        self.assertEqual(item["codigoCPBSAbrev"], self.dgi_product_code.code[:2])

    def test_government_invoice_requires_product_dgi_code(self):
        self.product_service.product_tmpl_id.dgi_code_id = False
        invoice = self._create_dgi_invoice(partner=self.partner_gobierno)
        with self.assertRaises(UserError) as error:
            invoice._validate_before_send_to_dgi()
        self.assertIn("government", str(error.exception).lower())
