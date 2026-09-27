from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    _inherit = "account.tax"

    hka_tax_code = fields.Selection(
        [
            ("00", "00 - 0% (Exento)"),
            ("01", "01 - 7%"),
            ("02", "02 - 10%"),
            ("03", "03 - 15%"),
            ("04", "04 - ISC"),
        ],
        string="HKA Tax Code",
        help="Tax code for HKA electronic invoicing (Panama DGI)",
    )

    hka_tax_isc_id = fields.Many2one(
        "account.tax.isc",
        string="HKA ISC",
        help="ISC for HKA electronic invoicing (Panama DGI)",
    )

    @api.constrains("hka_tax_code", "hka_tax_isc_id")
    def _check_hka_tax_code_consistency(self):
        for tax in self.filtered(lambda t: t.hka_tax_code == "04"):
            if not tax.hka_tax_isc_id:
                raise ValidationError(
                    _(
                        "If HKA Tax Code is '04' (ISC), you must also set the HKA ISC rate."
                    )
                )
