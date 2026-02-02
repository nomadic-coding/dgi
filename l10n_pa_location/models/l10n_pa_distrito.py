# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class L10nPaDistrito(models.Model):
    """Panama District (Distrito) - Second level administrative division"""

    _name = "l10n.pa.distrito"
    _description = "Panama District"
    _order = "code, name"
    _rec_name = "name"

    name = fields.Char(
        string="District Name",
        required=True,
        index=True,
        help="Name of the district (distrito)",
    )

    code = fields.Char(
        string="District Code",
        required=True,
        index=True,
        help="District code (second part of CODIGO_UBICACION: X-Y-Z)",
    )

    state_id = fields.Many2one(
        "res.country.state",
        string="Province",
        required=True,
        ondelete="cascade",
        domain="[('country_id.code', '=', 'PA')]",
        help="Province (Provincia) this district belongs to",
    )

    corregimiento_ids = fields.One2many(
        "l10n.pa.corregimiento",
        "distrito_id",
        string="Corregimientos",
        help="Corregimientos within this district",
    )

    corregimiento_count = fields.Integer(
        string="Number of Corregimientos",
        compute="_compute_corregimiento_count",
        store=True,
    )

    complete_name = fields.Char(
        string="Complete Name", compute="_compute_complete_name", store=True, index=True
    )

    country_id = fields.Many2one(
        "res.country", related="state_id.country_id", string="Country", store=True
    )

    @api.depends("corregimiento_ids")
    def _compute_corregimiento_count(self):
        for distrito in self:
            distrito.corregimiento_count = len(distrito.corregimiento_ids)

    @api.depends("name", "state_id.name")
    def _compute_complete_name(self):
        for distrito in self:
            if distrito.state_id:
                distrito.complete_name = f"{distrito.state_id.name} / {distrito.name}"
            else:
                distrito.complete_name = distrito.name

    @api.constrains("code", "state_id")
    def _check_unique_code_per_state(self):
        for distrito in self:
            domain = [
                ("code", "=", distrito.code),
                ("state_id", "=", distrito.state_id.id),
                ("id", "!=", distrito.id),
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    _("District code must be unique within the province!")
                )

    _sql_constraints = [
        (
            "code_state_uniq",
            "unique(code, state_id)",
            "District code must be unique per province!",
        ),
    ]
