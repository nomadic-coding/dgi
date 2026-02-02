from odoo import fields, models


class ResCountry(models.Model):
    _inherit = "res.country"

    dgi_code_id = fields.Many2one(
        comodel_name="dgi.code.mapping",
        string="DGI Country Code",
        domain=[("mapping_type", "=", "country")],
        help="DGI country code for Panama electronic invoicing",
    )
