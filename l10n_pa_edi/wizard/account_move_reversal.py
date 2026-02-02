# -*- coding: utf-8 -*-

from odoo import models


class AccountMoveReversal(models.TransientModel):
    """Override reversal wizard to set DGI document type for credit notes"""

    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        """Override to set hka_tipo_documento to '04' for credit notes"""
        res = super()._prepare_default_reversal(move)
        
        # If reversing a customer invoice (out_invoice), set document type to credit note (04)
        if move.move_type == "out_invoice":
            res["hka_tipo_documento"] = "04"  # Credit Note (E-bill)
            res["hka_tipo_documento_manual"] = False  # Allow auto-computation
        
        return res

