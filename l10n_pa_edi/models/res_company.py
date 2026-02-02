# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    dgi_codigo_sucursal_emisor = fields.Char(
        string="Código Sucursal Emisor",
        help="Branch code for DGI Panama (0000=Main, 0001+=Branch). Used in electronic invoicing.",
        size=4,
    )

    @api.constrains("dgi_codigo_sucursal_emisor")
    def _check_codigo_sucursal_unique(self):
        """Ensure branch code is unique per company"""
        for company in self:
            if company.dgi_codigo_sucursal_emisor:
                existing = self.search(
                    [
                        ("id", "!=", company.id),
                        (
                            "dgi_codigo_sucursal_emisor",
                            "=",
                            company.dgi_codigo_sucursal_emisor,
                        ),
                    ]
                )
                if existing:
                    raise ValidationError(
                        _("Branch code %s is already used by company %s")
                        % (company.dgi_codigo_sucursal_emisor, existing[0].name)
                    )
