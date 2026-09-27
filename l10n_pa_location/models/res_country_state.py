# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CountryState(models.Model):
    """Extended to represent Panama Provinces"""

    _inherit = "res.country.state"

    distrito_ids = fields.One2many(
        "l10n.pa.distrito",
        "state_id",
        string="Districts",
        help="Districts (Distritos) within this province",
    )

    district_count = fields.Integer(
        string="Number of Districts", compute="_compute_district_count", store=True
    )

    @api.depends("distrito_ids")
    def _compute_district_count(self):
        for state in self:
            state.district_count = len(state.distrito_ids)
