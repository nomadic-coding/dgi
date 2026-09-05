# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hka_api_url = fields.Char(
        related="company_id.hka_api_url",
        readonly=False,
    )
    hka_usuario = fields.Char(
        related="company_id.hka_usuario",
        readonly=False,
    )
    hka_clave = fields.Char(
        related="company_id.hka_clave",
        readonly=False,
    )
    hka_timeout = fields.Integer(
        related="company_id.hka_timeout",
        readonly=False,
    )
    hka_verify_ssl = fields.Boolean(
        related="company_id.hka_verify_ssl",
        readonly=False,
    )
