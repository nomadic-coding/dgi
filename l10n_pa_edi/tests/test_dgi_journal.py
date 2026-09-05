# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiJournal(L10nPaEdiTestCommon):
    def test_same_fiscal_point_allowed_on_another_branch(self):
        other = self.env["account.journal"].create({
            "name": "Branch 0001 Sales",
            "code": "S001",
            "type": "sale",
            "company_id": self.company.id,
            "dgi_codigo_sucursal_emisor": "0001",
            "dgi_punto_facturacion_fiscal": "001",
        })
        self.assertEqual(other.dgi_punto_facturacion_fiscal, "001")

    def test_same_branch_and_punto_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["account.journal"].create({
                "name": "Duplicate Point",
                "code": "SDUP",
                "type": "sale",
                "company_id": self.company.id,
                "dgi_codigo_sucursal_emisor": "0000",
                "dgi_punto_facturacion_fiscal": "001",
            })
