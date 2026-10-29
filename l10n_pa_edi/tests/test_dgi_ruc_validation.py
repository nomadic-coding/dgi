# -*- coding: utf-8 -*-

from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
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

        partner.with_context(dgi_ruc_validation=True).write({"dgi_ruc_validated": True})
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

    def _validated_partner(self):
        partner = self.env["res.partner"].create({
            **self._panama_address_vals(),
            "name": "Validated Co",
            "dgi_ruc": "155701888-2-2019",
            "dgi_tipo_ruc": "02",
        })
        partner._dgi_set_ruc_validated({
            "vat": "155701888-2-2019",
            "dgi_dv": "15",
        })
        self.assertTrue(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "01")
        return partner

    def test_changing_vat_resets_validation(self):
        partner = self._validated_partner()
        partner.write({"vat": "8-123-456"})
        self.assertFalse(partner.dgi_ruc_validated)
        self.assertFalse(partner.dgi_ruc_validation_date)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "02")

    def test_changing_dgi_ruc_or_tipo_resets_validation(self):
        partner = self._validated_partner()
        partner.write({"dgi_ruc": "8-123-456"})
        self.assertFalse(partner.dgi_ruc_validated)

        partner = self._validated_partner()
        partner.write({"dgi_tipo_ruc": "01"})
        self.assertFalse(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "02")

    def test_rewriting_same_vat_keeps_validation(self):
        partner = self._validated_partner()
        partner.write({"vat": " 155701888-2-2019 ", "name": "Renamed"})
        self.assertTrue(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "01")

    def test_clearing_vat_drops_to_consumidor_final(self):
        partner = self._validated_partner()
        partner.write({"vat": False})
        self.assertFalse(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_cliente_fe, "02")

    def test_validate_ruc_requires_invoicing_access(self):
        user = self.env["res.users"].create({
            "name": "No Invoice",
            "login": "dgi_no_invoice",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        api = self.env["l10n_pa_edi.hka_api"].with_user(user)
        with self.assertRaises(AccessError):
            api.validate_ruc("155701888-2-2019", "02")

    def test_validate_ruc_invoicing_user_reaches_api(self):
        api = self.env["l10n_pa_edi.hka_api"]
        with patch.object(
            type(api),
            "_make_request",
            return_value=(200, {
                "codigo": "200",
                "mensaje": "OK",
                "infoRuc": {
                    "tipoRuc": "02",
                    "razonSocial": "INVOICE USER SA",
                    "ruc": "155701888-2-2019",
                    "dv": "15",
                    "afiliadoFE": "Afiliado FE",
                },
            }),
        ) as request, patch.object(
            type(self.env["hka.api.log"]),
            "log_api_call",
            return_value=None,
        ):
            result = api.validate_ruc("155701888-2-2019", "02")
        request.assert_called_once()
        self.assertTrue(result["valid"])

    def test_gobierno_validate_ruc_keeps_tipo_03(self):
        partner = self.env["res.partner"].create({
            **self._panama_address_vals(),
            "name": "Ministerio Test",
            "is_company": True,
            "dgi_ruc": "123456789-1-2020",
            "dgi_tipo_ruc": "03",
        })
        result = {
            "valid": True,
            "dv": "08",
            "tipo_ruc": "02",
            "razonSocial": "MINISTERIO TEST",
            "status": "Afiliado FE",
        }
        with patch.object(
            type(self.env["l10n_pa_edi.hka_api"]),
            "validate_ruc",
            return_value=result,
        ) as mocked:
            partner.action_validate_ruc()
        self.assertEqual(mocked.call_args.args[1], "02")
        self.assertTrue(partner.dgi_ruc_validated)
        self.assertEqual(partner.dgi_tipo_ruc, "03")
        self.assertEqual(partner.dgi_tipo_cliente_fe, "03")

    def test_gobierno_without_ruc_consult_cannot_send(self):
        partner = self.env["res.partner"].create({
            **self._panama_address_vals(),
            "name": "Gobierno Sin Consulta",
            "is_company": True,
            "vat": "123456789-1-2020",
            "dgi_ruc": "123456789-1-2020",
            "dgi_tipo_ruc": "03",
            "dgi_dv": "08",
            "dgi_razon_social": "GOBIERNO SIN CONSULTA",
        })
        self.assertEqual(partner.dgi_tipo_cliente_fe, "03")
        self.assertFalse(partner.dgi_ruc_validated)
        invoice = self._create_dgi_invoice(partner=partner)
        with self.assertRaises(UserError) as error:
            invoice._prepare_dgi_document_data()
        self.assertIn("ConsultaRucDv", error.exception.args[0])
