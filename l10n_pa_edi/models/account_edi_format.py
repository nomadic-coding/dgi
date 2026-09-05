# -*- coding: utf-8 -*-

import json

from odoo import _, models
from odoo.exceptions import UserError


class AccountEdiFormat(models.Model):
    _inherit = "account.edi.format"

    def _needs_web_services(self):
        return self.code == "pa_dgi_hka" or super()._needs_web_services()

    def _is_compatible_with_journal(self, journal):
        if self.code != "pa_dgi_hka":
            return super()._is_compatible_with_journal(journal)
        return journal.type == "sale" and journal.country_code == "PA"

    def _is_enabled_by_default_on_journal(self, journal):
        if self.code != "pa_dgi_hka":
            return super()._is_enabled_by_default_on_journal(journal)
        return bool(journal.use_dgi_electronic_invoicing)

    def _check_move_configuration(self, move):
        # Invoice-level HKA checks run in the post callable so posting is not blocked.
        return super()._check_move_configuration(move)

    def _get_move_applicability(self, move):
        self.ensure_one()
        if self.code != "pa_dgi_hka":
            return super()._get_move_applicability(move)
        if (
            move.move_type in ("out_invoice", "out_refund")
            and move.journal_id.use_dgi_electronic_invoicing
        ):
            return {
                "post": self._l10n_pa_edi_post_invoice,
                "cancel": self._l10n_pa_edi_cancel_invoice,
                "edi_content": self._l10n_pa_edi_json_content,
            }
        return None

    def _l10n_pa_edi_json_content(self, move):
        return json.dumps(
            move._prepare_dgi_document_data(),
            ensure_ascii=False,
        ).encode()

    def _l10n_pa_edi_post_invoice(self, moves):
        return {move: self._l10n_pa_edi_post_invoice_one(move) for move in moves}

    def _l10n_pa_edi_post_invoice_one(self, move):
        if move.dgi_cufe and move.dgi_status in ("procesado", "anulado"):
            return {"success": True}

        try:
            move._validate_before_send_to_dgi()
            document_data = move._prepare_dgi_document_data()
            result = move._send_to_dgi_internal(document_data=document_data)
        except UserError as err:
            return {"error": str(err), "blocking_level": "error"}
        if result.get("success"):
            attachment = self.env["ir.attachment"].create({
                "name": "%s_hka.json" % (move.name or move.id),
                "raw": json.dumps(document_data, ensure_ascii=False).encode(),
                "mimetype": "application/json",
                "res_model": move._name,
                "res_id": move.id,
            })
            move.message_post(
                body=_("Document sent to DGI successfully. CUFE: %s")
                % (result.get("dgi_cufe") or _("Pending")),
                message_type="notification",
            )
            return {"success": True, "attachment": attachment}

        error_message = (
            result.get("error_message")
            or result.get("mensaje")
            or _("Unknown error")
        )
        move.message_post(
            body=_("DGI Error: %s") % error_message,
            message_type="notification",
        )
        return {"error": error_message, "blocking_level": "error"}

    def _l10n_pa_edi_cancel_invoice(self, moves):
        return {move: self._l10n_pa_edi_cancel_invoice_one(move) for move in moves}

    def _l10n_pa_edi_cancel_invoice_one(self, move):
        if move.dgi_status == "anulado":
            return {"success": True}

        motivo = (move.hka_motivo_anulacion or "").strip()
        if len(motivo) < 20 or len(motivo) > 500:
            return {
                "error": _(
                    "A cancellation reason between 20 and 500 characters is required "
                    "to cancel this invoice in DGI."
                ),
                "blocking_level": "error",
            }
        if not move.dgi_cufe:
            return {
                "error": _(
                    "Cannot cancel invoice: CUFE not available. "
                    "The invoice may not have been successfully sent to DGI."
                ),
                "blocking_level": "error",
            }

        anulacion_data = {
            "motivoAnulacion": motivo,
            "datosDocumento": {
                "codigoSucursalEmisor": move.journal_id.dgi_codigo_sucursal_emisor or "",
                "numeroDocumentoFiscal": move.name or "",
                "puntoFacturacionFiscal": (
                    move.journal_id.dgi_punto_facturacion_fiscal or "001"
                ).zfill(3),
                "serialDispositivo": "",
                "tipoDocumento": move.hka_tipo_documento or "01",
                "tipoEmision": move.hka_tipo_emision or "01",
            },
        }
        result = self.env["l10n_pa_edi.hka_api"].anular(
            anulacion_data, move_id=move.id
        )
        if not result.get("success"):
            error_message = (
                result.get("error_message")
                or result.get("mensaje")
                or _("Unknown error")
            )
            return {"error": error_message, "blocking_level": "error"}

        move._dgi_commit_api_fields({
            "dgi_status": "anulado",
            "dgi_error_message": False,
        })
        return {"success": True}
