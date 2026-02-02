from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    dgi_code_id = fields.Many2one(
        comodel_name="dgi.code.mapping",
        string="DGI Product/Service Code",
        domain=[("mapping_type", "=", "product_service")],
        help="DGI code for product or service classification in Panama",
    )
