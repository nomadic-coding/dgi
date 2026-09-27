# -*- coding: utf-8 -*-

from odoo import fields, models

from odoo.addons.l10n_pa_edi.models.hka_combinations import HKA_FORMA_PAGO_SELECTION


class ResCompany(models.Model):
    _inherit = "res.company"

    dgi_codigo_sucursal_emisor = fields.Char(
        string="Código Sucursal Emisor",
        help="Default branch code for DGI Panama (0000=Main, 0001+=Branch). "
        "Journals keep their own sucursal / punto pair; this is only a company default.",
        size=4,
    )

    hka_api_url = fields.Char(
        string="HKA API URL",
        default="https://demointegracion.thefactoryhka.com.pa",
        help="The Factory HKA API endpoint URL",
    )
    hka_usuario = fields.Char(
        string="HKA Usuario",
        groups="base.group_system",
        copy=False,
        help="HKA API username/user token",
    )
    hka_clave = fields.Char(
        string="HKA Clave",
        groups="base.group_system",
        copy=False,
        help="HKA API password",
    )
    hka_timeout = fields.Integer(
        string="API Timeout (seconds)",
        default=30,
    )
    hka_verify_ssl = fields.Boolean(
        string="Verify SSL",
        default=True,
    )
    hka_merge_same_dgi_code = fields.Boolean(
        string="Merge Same DGI Code Lines",
        default=True,
        help="Default for new invoices: group e-factura lines that share the "
        "same DGI product/service code (and the same ITBMS/ISC) into one line "
        "sent as quantity 1 with the net total as unit price.",
    )
    hka_forma_pago = fields.Selection(
        HKA_FORMA_PAGO_SELECTION,
        string="Default Payment Method",
        default="01",
        help="Default DGI payment method for new invoices. Credit (01) means "
        "the sale is on account; plazos come from the payment term.",
    )
    hka_auth_token = fields.Char(
        string="HKA Auth Token",
        groups="base.group_system",
        copy=False,
    )
    hka_auth_token_expiry = fields.Char(
        string="HKA Auth Token Expiry",
        groups="base.group_system",
        copy=False,
    )
