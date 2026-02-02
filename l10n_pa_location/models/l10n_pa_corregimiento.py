# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class L10nPaCorregimiento(models.Model):
    """Panama Corregimiento - Third level administrative division"""

    _name = "l10n.pa.corregimiento"
    _description = "Panama Corregimiento"
    _order = "codigo_ubicacion, name"
    _rec_name = "name"

    name = fields.Char(
        string="Corregimiento Name",
        required=True,
        index=True,
        help="Name of the corregimiento",
    )

    code = fields.Char(
        string="Corregimiento Code",
        required=True,
        index=True,
        help="Corregimiento code (third part of CODIGO_UBICACION: X-Y-Z)",
    )

    codigo_ubicacion = fields.Char(
        string="Location Code (CODIGO_UBICACION)",
        required=True,
        index=True,
        help="Complete location code in format: PROVINCIA-DISTRITO-CORREGIMIENTO (e.g., 8-8-1)",
    )

    distrito_id = fields.Many2one(
        "l10n.pa.distrito",
        string="District",
        required=True,
        ondelete="cascade",
        help="District (Distrito) this corregimiento belongs to",
    )

    state_id = fields.Many2one(
        "res.country.state",
        related="distrito_id.state_id",
        string="Province",
        store=True,
        help="Province (Provincia) this corregimiento belongs to",
    )

    country_id = fields.Many2one(
        "res.country", related="state_id.country_id", string="Country", store=True
    )

    complete_name = fields.Char(
        string="Complete Name", compute="_compute_complete_name", store=True, index=True
    )

    is_cabecera = fields.Boolean(
        string="Is Cabecera",
        help="Indicates if this is the district head (cabecera)",
        default=False,
    )

    @api.depends("name", "distrito_id.name", "state_id.name")
    def _compute_complete_name(self):
        for corregimiento in self:
            if corregimiento.distrito_id and corregimiento.state_id:
                corregimiento.complete_name = (
                    f"{corregimiento.state_id.name} / "
                    f"{corregimiento.distrito_id.name} / "
                    f"{corregimiento.name}"
                )
            elif corregimiento.distrito_id:
                corregimiento.complete_name = (
                    f"{corregimiento.distrito_id.name} / {corregimiento.name}"
                )
            else:
                corregimiento.complete_name = corregimiento.name

    @api.constrains("codigo_ubicacion")
    def _check_unique_codigo_ubicacion(self):
        for corregimiento in self:
            domain = [
                ("codigo_ubicacion", "=", corregimiento.codigo_ubicacion),
                ("id", "!=", corregimiento.id),
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(
                    _("CODIGO_UBICACION must be unique! Code %s already exists.")
                    % corregimiento.codigo_ubicacion
                )

    @api.constrains("codigo_ubicacion", "distrito_id", "state_id")
    def _check_codigo_ubicacion_format(self):
        """Validate that codigo_ubicacion matches the hierarchy"""
        for corregimiento in self:
            if not corregimiento.codigo_ubicacion:
                continue

            parts = corregimiento.codigo_ubicacion.split("-")
            if len(parts) != 3:
                raise ValidationError(
                    _("CODIGO_UBICACION must be in format X-Y-Z (e.g., 8-8-1)")
                )

    _sql_constraints = [
        (
            "codigo_ubicacion_uniq",
            "unique(codigo_ubicacion)",
            "Location code (CODIGO_UBICACION) must be unique!",
        ),
    ]
