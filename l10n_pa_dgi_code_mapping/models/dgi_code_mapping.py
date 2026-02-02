from odoo import api, fields, models
from odoo.osv import expression


class DgiCodeMapping(models.Model):
    _name = "dgi.code.mapping"
    _description = "Panama DGI Code Mapping"
    _rec_name = "display_name"

    code = fields.Char(
        string="Code",
        required=True,
    )
    name = fields.Char(
        string="Name",
        required=True,
    )

    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
    )

    description = fields.Text(
        string="Description",
        help="Description of the code.",
    )

    mapping_type = fields.Selection(
        [
            ("unit_of_measure", "Unit of Measure"),
            ("country", "Country"),
            ("incoterm", "Incoterm"),
            ("currency", "Currency"),
            ("product_service", "Product Service"),
        ],
        string="Mapping Type",
        required=True,
    )

    _sql_constraints = [
        (
            "code_uniq",
            "unique(code, mapping_type)",
            "The code must be unique for each mapping type.",
        ),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for record in self:
            if record.code:
                record.display_name = f"[{record.code}] {record.name}"
            else:
                record.display_name = record.name or ""

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """Allow searching by code or name"""
        if args is None:
            args = []

        if name:
            name_domain = [
                "|",
                ("code", operator, name),
                ("name", operator, name),
            ]
            domain = expression.AND([name_domain, args])
        else:
            domain = args

        records = self.search(domain, limit=limit)
        records.fetch(['display_name'])
        return [(record.id, record.display_name) for record in records]
