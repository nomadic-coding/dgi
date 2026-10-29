# -*- coding: utf-8 -*-

import time

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
        self.assertNotIn("visible", log.request_data)
        self.assertIn("***", log.response_data)
        self.assertIn("200", log.response_data)

    def test_log_api_call_does_not_block_on_locked_invoice(self):
        """Detached logs carry no move FK, so they cannot wait on the Enviar
        invoice row lock. (TransactionCase cannot open a real second
        connection; this checks the row shape and the key-based linking.)"""
        invoice = self._create_dgi_invoice(partner=self.partner_contribuyente)
        self.env.cr.execute(
            "SELECT id FROM account_move WHERE id = %s FOR UPDATE",
            [invoice.id],
        )
        started = time.monotonic()
        log_id = self.env["hka.api.log"].log_api_call(
            api_method="enviar",
            request_data={"ok": True},
            response_data={"codigo": "200"},
            status="success",
            move_id=invoice.id,
            auto_commit=True,
        )
        self.assertLess(time.monotonic() - started, 8)
        self.assertTrue(log_id, "detached log row must be created")
        log = self.env["hka.api.log"].browse(log_id)
        self.assertFalse(log.move_id, "detached rows never carry the move FK")
        self.assertEqual(
            log.document_key,
            self.env["hka.api.log"]._document_key_from_move(invoice),
        )
        self.assertEqual(log.document_number, invoice.name)
        invoice.invalidate_recordset(["hka_api_log_count"])
        self.assertEqual(invoice.hka_api_log_count, 1)
        self.assertIn(log, self.env["hka.api.log"].search(invoice._hka_api_log_domain()))
        with self.env.registry.cursor() as cr:
            cr.execute(
                """
                DELETE FROM hka_api_log
                WHERE request_data LIKE %s
                """,
                ['%{"ok": true}%'],
            )
            cr.commit()
