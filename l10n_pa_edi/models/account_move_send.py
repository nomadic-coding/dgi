# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    @api.model
    def _get_mail_attachment_from_doc(self, doc):
        if doc.edi_format_id.code == "pa_dgi_hka":
            return self.env["ir.attachment"]
        return super()._get_mail_attachment_from_doc(doc)
