from odoo import api, fields, models


class DgiCodeMapping(models.Model):
    _name = "dgi.code.mapping"
    _description = "Panama DGI Code Mapping"
    _rec_names_search = ["code", "name"]

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
