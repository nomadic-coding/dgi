# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    """Extended to include Panama location fields"""

    _inherit = "res.partner"

    # Panama location fields
    l10n_pa_distrito_id = fields.Many2one(
        "l10n.pa.distrito",
        string="District (Distrito)",
        ondelete="restrict",
        domain="[('state_id', '=', state_id)]",
        help="District (Distrito) within the selected province",
    )

    l10n_pa_corregimiento_id = fields.Many2one(
        "l10n.pa.corregimiento",
        string="Corregimiento",
        ondelete="restrict",
        domain="[('distrito_id', '=', l10n_pa_distrito_id)]",
        help="Corregimiento within the selected district",
    )

    l10n_pa_codigo_ubicacion = fields.Char(
        string="Location Code",
        related="l10n_pa_corregimiento_id.codigo_ubicacion",
        store=True,
        readonly=True,
        help="Official location code (CODIGO_UBICACION) for DGI documents",
    )

    # Computed display field for easier reading
    l10n_pa_location_display = fields.Char(
        string="Complete Location",
        compute="_compute_l10n_pa_location_display",
        help="Complete Panama location hierarchy for display",
    )

    @api.depends("state_id", "l10n_pa_distrito_id", "l10n_pa_corregimiento_id")
    def _compute_l10n_pa_location_display(self):
        for partner in self:
            parts = []
            if partner.l10n_pa_corregimiento_id:
                parts.append(partner.l10n_pa_corregimiento_id.name)
            if partner.l10n_pa_distrito_id:
                parts.append(partner.l10n_pa_distrito_id.name)
            if partner.state_id:
                parts.append(partner.state_id.name)

            if parts:
                partner.l10n_pa_location_display = " / ".join(parts)
            else:
                partner.l10n_pa_location_display = ""

    @api.onchange("state_id")
    def _onchange_state_id_l10n_pa(self):
        """Clear district and corregimiento when province changes"""
        if self.country_id and self.country_id.code == "PA":
            if self.state_id:
                # If the current distrito doesn't belong to the new state, clear it
                if (
                    self.l10n_pa_distrito_id
                    and self.l10n_pa_distrito_id.state_id != self.state_id
                ):
                    self.l10n_pa_distrito_id = False
                    self.l10n_pa_corregimiento_id = False
            else:
                self.l10n_pa_distrito_id = False
                self.l10n_pa_corregimiento_id = False

    @api.onchange("l10n_pa_distrito_id")
    def _onchange_l10n_pa_distrito_id(self):
        """Clear corregimiento when district changes"""
        if self.country_id and self.country_id.code == "PA":
            if self.l10n_pa_distrito_id:
                # If the current corregimiento doesn't belong to the new distrito, clear it
                if (
                    self.l10n_pa_corregimiento_id
                    and self.l10n_pa_corregimiento_id.distrito_id
                    != self.l10n_pa_distrito_id
                ):
                    self.l10n_pa_corregimiento_id = False
            else:
                self.l10n_pa_corregimiento_id = False

    @api.onchange("country_id")
    def _onchange_country_id_l10n_pa(self):
        """Clear Panama-specific fields when country changes from Panama"""
        if self.country_id and self.country_id.code != "PA":
            if self.l10n_pa_distrito_id or self.l10n_pa_corregimiento_id:
                self.l10n_pa_distrito_id = False
                self.l10n_pa_corregimiento_id = False
