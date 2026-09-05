# -*- coding: utf-8 -*-

from odoo import fields, models


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
