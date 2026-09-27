# -*- coding: utf-8 -*-

from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiCompanyConfig(L10nPaEdiTestCommon):
    def test_get_config_reads_company_not_icp(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_pa_edi.hka_usuario", "icp-user"
        )
        self.company.hka_usuario = "company-user"
        config = self.env["l10n_pa_edi.hka_api"]._get_config(company=self.company)
        self.assertEqual(config["usuario"], "company-user")
        self.assertEqual(config["api_url"], "https://hka.test.example")

    def test_auto_map_fills_empty_catalog_links(self):
        self.country_pa.dgi_code_id = False
        self.uom_unit.dgi_code_id = False
        self.env.ref("base.USD").dgi_code_id = False
        self.tax_itbms_7.hka_tax_code = False

        self.env["l10n_pa_edi.hka_api"]._auto_map_defaults()

        self.assertTrue(self.country_pa.dgi_code_id)
        self.assertTrue(self.uom_unit.dgi_code_id)
        self.assertTrue(self.env.ref("base.USD").dgi_code_id)
        self.assertEqual(self.tax_itbms_7.hka_tax_code, "01")
