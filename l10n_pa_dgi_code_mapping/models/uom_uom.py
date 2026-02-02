from odoo import fields, models


class UomUom(models.Model):
    _inherit = "uom.uom"

    dgi_code_id = fields.Many2one(
        comodel_name="dgi.code.mapping",
        string="DGI Unit of Measure Code",
        domain=[("mapping_type", "=", "unit_of_measure")],
        help="DGI unit of measure code for Panama electronic invoicing",
    )
