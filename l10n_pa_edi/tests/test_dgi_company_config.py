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
