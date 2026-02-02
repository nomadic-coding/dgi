from odoo import fields, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    dgi_code_id = fields.Many2one(
        comodel_name="dgi.code.mapping",
        string="DGI Currency Code",
        domain=[("mapping_type", "=", "currency")],
        help="DGI currency code for Panama electronic invoicing",
    )
