from odoo import fields, models


class AccountIncoterms(models.Model):
    _inherit = "account.incoterms"

    dgi_code_id = fields.Many2one(
        comodel_name="dgi.code.mapping",
        string="DGI Incoterm Code",
        domain=[("mapping_type", "=", "incoterm")],
        help="DGI incoterm code for Panama electronic invoicing",
    )
