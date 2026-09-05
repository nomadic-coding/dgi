# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiApiLogSecurity(L10nPaEdiTestCommon):
    def test_internal_user_cannot_create_api_log(self):
        user = self.env["res.users"].create({
            "name": "DGI Internal",
            "login": "dgi_internal_log",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        Log = self.env["hka.api.log"].with_user(user)
        with self.assertRaises(AccessError):
            Log.create({
                "api_method": "enviar",
                "status": "success",
                "company_id": self.company.id,
            })

    def test_log_api_call_redacts_credentials(self):
        self.env["hka.api.log"].log_api_call(
            api_method="enviar",
            request_data={"usuario": "visible", "clave": "secret"},
            response_data={"token": "jwt-secret", "codigo": "200"},
            status="success",
            auto_commit=False,
        )
        log = self.env["hka.api.log"].search([("api_method", "=", "enviar")], limit=1)
        self.assertIn("***", log.request_data)
        self.assertNotIn("secret", log.request_data)
        self.assertIn("***", log.response_data)
        self.assertIn("200", log.response_data)
