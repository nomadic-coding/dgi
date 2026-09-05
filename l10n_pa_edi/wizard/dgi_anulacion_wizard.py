# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
        """Cancel the invoice in DGI first, then cancel it in Odoo."""
        self.ensure_one()
        move = self.move_id

        if not move.dgi_sent:
            raise UserError(_("This invoice has not been sent to DGI yet."))

        if not move.dgi_cufe:
            raise UserError(
                _(
                    "Cannot cancel invoice: CUFE not available. The invoice may not have been successfully sent to DGI."
                )
            )

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

        anulacion_data = {
            "motivoAnulacion": motivo_anulacion_clean,
            "datosDocumento": {
                "codigoSucursalEmisor": self.codigo_sucursal_emisor or "",
                "numeroDocumentoFiscal": self.numero_documento_fiscal or "",
                "puntoFacturacionFiscal": (self.punto_facturacion_fiscal.zfill(3)),
                "serialDispositivo": "",
                "tipoDocumento": self.tipo_documento,
                "tipoEmision": self.tipo_emision,
            },
        }

        hka_api = self.env["l10n_pa_edi.hka_api"]
        result = hka_api.anular(anulacion_data, move_id=move.id)

        if not result.get("success"):
            error_message = (
                result.get("error_message")
                or result.get("mensaje")
                or _("Unknown error")
            )
            raise UserError(
                _(
                    "Failed to cancel the invoice in DGI: %s. "
                    "The invoice was not canceled in Odoo."
                )
                % error_message
            )

        move.write(
            {
                "dgi_status": "anulado",
                "dgi_error_message": False,
            }
        )
        move.with_context(force_dgi_cancel=True).button_cancel()
        move.message_post(
            body=_("Invoice successfully canceled in DGI. Reason: %s")
            % self.motivo_anulacion,
            message_type="notification",
        )
        return True
