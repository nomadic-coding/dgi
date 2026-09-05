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
