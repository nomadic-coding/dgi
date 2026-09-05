# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiRucValidation(L10nPaEdiTestCommon):
    def test_cannot_mark_ruc_validated_by_hand(self):
        partner = self.env["res.partner"].create({
            **self._panama_address_vals(),
            "name": "Fake Taxpayer",
            "vat": "155701888-2-2019",
            "dgi_ruc": "155701888-2-2019",
            "dgi_tipo_ruc": "02",
            "dgi_ruc_validated": True,
        })
        self.assertFalse(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "02")

        partner.write({"dgi_ruc_validated": True})
        self.assertFalse(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "02")

    def test_validate_ruc_sets_flag(self):
        partner = self.env["res.partner"].create({
            **self._panama_address_vals(),
            "name": "To Validate",
            "dgi_ruc": "155701888-2-2019",
            "dgi_tipo_ruc": "02",
        })
        result = {
            "valid": True,
            "dv": "15",
            "tipo_ruc": "02",
            "razonSocial": "TO VALIDATE S.A.",
            "status": "Afiliado FE",
        }
        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "validate_ruc",
            return_value=result,
        ):
            partner.action_validate_ruc()

        self.assertTrue(partner.dgi_ruc_validated)
        self.assertEqual(partner.vat, "155701888-2-2019")
        self.assertEqual(partner.dgi_dv, "15")
        self.assertEqual(partner.dgi_tipo_cliente_fe, "01")
