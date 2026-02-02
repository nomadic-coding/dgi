from odoo import api, fields, models


class AccountTaxIsc(models.Model):
    _name = "account.tax.isc"
    _description = "Account Tax ISC"
    _rec_name = "name"

    name = fields.Char(string="Name", required=True)
    rate = fields.Float(string="Rate", required=True)
    active = fields.Boolean(string="Active", default=True)
