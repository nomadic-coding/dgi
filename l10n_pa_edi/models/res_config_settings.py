# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # HKA API Configuration
    hka_api_url = fields.Char(
        string="HKA API URL",
        config_parameter="l10n_pa_edi.hka_api_url",
        default="https://demointegracion.thefactoryhka.com.pa",
        help="The Factory HKA API endpoint URL",
    )
    hka_usuario = fields.Char(
        string="HKA Usuario",
        config_parameter="l10n_pa_edi.hka_usuario",
        help="HKA API username/user token",
    )
    hka_clave = fields.Char(
        string="HKA Clave",
        config_parameter="l10n_pa_edi.hka_clave",
        help="HKA API password",
    )
    hka_timeout = fields.Integer(
        string="API Timeout (seconds)",
        config_parameter="l10n_pa_edi.hka_timeout",
        default=30,
    )
    hka_verify_ssl = fields.Boolean(
        string="Verify SSL",
        config_parameter="l10n_pa_edi.hka_verify_ssl",
        default=True,
    )

