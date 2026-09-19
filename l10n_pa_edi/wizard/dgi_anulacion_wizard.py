# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mail import html2plaintext


class DgiAnulacionWizard(models.TransientModel):
    """Wizard for canceling invoices sent to DGI"""

    _name = "dgi.anulacion.wizard"
    _description = "DGI Cancellation Wizard"

    move_id = fields.Many2one(
        "account.move",
        string="Invoice",
        required=True,
        readonly=True,
    )

    motivo_anulacion = fields.Text(
        string="Cancellation Reason",
        required=True,
        help="Reason for canceling this invoice (minimum 20 characters, maximum 500 characters)",
    )

    # Document data fields (readonly, for display)
    codigo_sucursal_emisor = fields.Char(
        string="Branch Code",
        readonly=True,
    )
    numero_documento_fiscal = fields.Char(
        string="Document Number",
        readonly=True,
    )
    punto_facturacion_fiscal = fields.Char(
        string="Fiscal Point",
        readonly=True,
    )
    tipo_documento = fields.Char(
        string="Document Type",
        readonly=True,
    )
    tipo_emision = fields.Char(
        string="Emission Type",
        readonly=True,
    )

    @api.constrains("motivo_anulacion")
    def _check_motivo_anulacion_length(self):
        """Validate motivoAnulacion length according to API requirements"""
        for record in self:
            if not record.motivo_anulacion:
                continue
            motivo_clean = record.motivo_anulacion.strip()
            motivo_length = len(motivo_clean)

            if motivo_length < 20:
                raise UserError(
                    _(
                        "Cancellation reason must be at least 20 characters long. Current length: %d characters."
                    )
                    % motivo_length
                )

            if motivo_length > 500:
                raise UserError(
                    _(
                        "Cancellation reason must not exceed 500 characters. Current length: %d characters."
                    )
                    % motivo_length
                )

    @api.model
    def default_get(self, fields_list):
        """Set default values from the invoice"""
        res = super().default_get(fields_list)
        active_id = self.env.context.get("active_id")
        if active_id:
            move = self.env["account.move"].browse(active_id)
            res["move_id"] = move.id
            res["codigo_sucursal_emisor"] = (
                move.journal_id.dgi_codigo_sucursal_emisor or ""
            )
            res["numero_documento_fiscal"] = move.name or ""
            res["punto_facturacion_fiscal"] = (
                move.journal_id.dgi_punto_facturacion_fiscal or "001"
            )
            res["tipo_documento"] = move.hka_tipo_documento or "01"
            res["tipo_emision"] = move.hka_tipo_emision or "01"
        return res

    def action_anular(self):
        """Store the motivo, mark the HKA EDI document to cancel, then process it."""
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only accounting managers can cancel invoices in DGI."))

        move = self.move_id
        move.check_access_rights("write")
        move.check_access_rule("write")

        if not move.dgi_sent:
            raise UserError(_("This invoice has not been sent to DGI yet."))

        if not move.dgi_cufe:
            raise UserError(
                _(
                    "Cannot cancel invoice: CUFE not available. The invoice may not have been successfully sent to DGI."
                )
            )

        window_error = move._dgi_anulacion_window_error()
        if window_error:
            raise UserError(window_error)

        if not self.motivo_anulacion:
            raise UserError(_("Please provide a cancellation reason."))

        motivo_anulacion_clean = (self.motivo_anulacion or "").strip()
        motivo_length = len(motivo_anulacion_clean)

        if motivo_length < 20:
            raise UserError(
                _(
                    "Cancellation reason must be at least 20 characters long. Current length: %d characters."
                )
                % motivo_length
            )

        if motivo_length > 500:
            raise UserError(
                _(
                    "Cancellation reason must not exceed 500 characters. Current length: %d characters."
                )
                % motivo_length
            )

        move.write({"hka_motivo_anulacion": motivo_anulacion_clean})

        edi_docs = move._l10n_pa_hka_edi_documents().filtered(
            lambda doc: doc.state == "sent"
        )
        if not edi_docs:
            raise UserError(_("This invoice has no HKA electronic document to cancel."))

        edi_docs.write({"state": "to_cancel", "error": False, "blocking_level": False})
        move.action_process_edi_web_services(with_commit=False)
        move.invalidate_recordset([
            "dgi_status",
            "dgi_error_message",
            "edi_state",
            "edi_error_message",
            "state",
        ])
        if move.dgi_status != "anulado":
            error_message = html2plaintext(
                move.edi_error_message or move.dgi_error_message or _("Unknown error")
            )
            raise UserError(
                _(
                    "Failed to cancel the invoice in DGI: %s. "
                    "The invoice was not canceled in Odoo."
                )
                % error_message
            )

        move.message_post(
            body=_("Invoice successfully canceled in DGI. Reason: %s")
            % self.motivo_anulacion,
            message_type="notification",
        )
        return True
