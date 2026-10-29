# -*- coding: utf-8 -*-

from odoo import models


class AccountMoveReversal(models.TransientModel):
    """Override reversal wizard so credit notes get DGI document type 04"""

    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        res = super()._prepare_default_reversal(move)

        if move.move_type == "out_invoice":
            # Do not pass hka_tipo_documento here: its inverse would flag the
            # credit note as manual. With reversed_entry_id set, the compute
            # yields 04 (Credit Note referencing the e-factura) on its own.
            res["hka_tipo_documento_manual"] = False

        return res
