# -*- coding: utf-8 -*-

from odoo import models


class AccountEdiDocument(models.Model):
    _inherit = "account.edi.document"

    def _filter_edi_attachments_for_mailing(self):
        """HKA JSON is an API payload, not a customer e-factura file."""
        self.ensure_one()
        if self.edi_format_id.code == "pa_dgi_hka":
            return {}
        return super()._filter_edi_attachments_for_mailing()
