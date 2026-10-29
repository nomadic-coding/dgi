# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountMoveDgi(models.Model):
    _inherit = "account.move"

    def _prepare_dgi_document_data(self):
        return self.env["l10n.pa.edi.payload"].prepare(self)

    def _validate_before_send_to_dgi(self):
        return self.env["l10n.pa.edi.payload"].validate_for_send(self)

    def _dgi_referenced_cufe_errors(self):
        return self.env["l10n.pa.edi.payload"]._dgi_referenced_cufe_errors(self)

    def _dgi_product_line_tax_errors(self):
        return self.env["l10n.pa.edi.payload"]._dgi_product_line_tax_errors(self)

    def _dgi_requires_product_line_taxes(self):
        return self.env["l10n.pa.edi.payload"]._dgi_requires_product_line_taxes(self)

    def _check_dgi_product_line_taxes(self):
        return self.env["l10n.pa.edi.payload"]._check_dgi_product_line_taxes(self)

    def _dgi_hka_tax_mapping_errors(self, tax):
        return self.env["l10n.pa.edi.payload"]._dgi_hka_tax_mapping_errors(tax)

    def _dgi_credit_payment_errors(self):
        return self.env["l10n.pa.edi.payload"]._dgi_credit_payment_errors(self)

    def _check_dgi_credit_payment(self):
        return self.env["l10n.pa.edi.payload"]._check_dgi_credit_payment(self)

    def _l10n_pa_hka_edi_documents(self):
        return self.edi_document_ids.filtered(
            lambda doc: doc.edi_format_id.code == "pa_dgi_hka"
        )

    def _send_to_dgi_internal(self, document_data=None):
        """Send the invoice payload to HKA and persist the DGI response fields."""
        self.ensure_one()

        # Do not FOR UPDATE this move here. account.edi already locks the EDI
        # document, and an exclusive lock deadlocks the independent HKA log /
        # CUFE cursors that insert against this row.
        self.invalidate_recordset(["dgi_status", "dgi_cufe"])
        if self.dgi_cufe and self._dgi_status_is("procesado", "anulado"):
            raise UserError(_("This document has already been sent to DGI"))

        hka_api = self.env["l10n_pa_edi.hka_api"]
        if document_data is None:
            document_data = self._prepare_dgi_document_data()
        result = hka_api.enviar(document_data, move_id=self.id)
        if result.get("success") and not result.get("dgi_cufe"):
            result = dict(result)
            result["success"] = False
            result["status"] = "Error: missing CUFE"
            result["error_message"] = result.get("error_message") or _(
                "HKA accepted the request but did not return a CUFE."
            )

        fields_to_write = {
            "dgi_status": result["status"],
            "dgi_error_message": result["error_message"],
        }
        if result["success"]:
            fields_to_write.update({
                "dgi_sent_date": fields.Datetime.now(),
                "dgi_cufe": result["dgi_cufe"],
                "dgi_qr": result["dgi_qr"],
                "dgi_fecha_recepcion": result["dgi_fecha_recepcion"],
                "dgi_protocolo_autorizacion": result["dgi_protocolo_autorizacion"],
            })
            self._dgi_commit_api_fields(fields_to_write)
        else:
            self._dgi_write_api_fields(fields_to_write)

        return result

    def action_send_to_dgi(self):
        """Process the HKA EDI document now (manual trigger / tests)."""
        self.ensure_one()
        if self.state != "posted":
            raise UserError(_("Only posted invoices can be sent to DGI"))
        if self.dgi_sent:
            raise UserError(_("This document has already been sent to DGI"))
        if not self._l10n_pa_hka_edi_documents().filtered(lambda doc: doc.state == "to_send"):
            raise UserError(
                _("DGI Electronic Invoicing is not enabled for this journal")
            )
        self.action_process_edi_web_services(with_commit=False)
        return True

    def _need_cancel_request(self):
        """Block direct cancel of a procesado e-factura; allow it after DGI anulación."""
        if self._dgi_status_is("anulado"):
            return False
        if self._dgi_status_is("procesado") and self.dgi_sent:
            return True
        return super()._need_cancel_request()

    def button_request_cancel(self):
        """Override to open DGI cancellation wizard when invoice is sent to DGI"""
        # If invoice is sent to DGI, use DGI cancellation wizard
        if self.dgi_sent and self._dgi_status_is("procesado"):
            return self.action_cancel_dgi()
        return super().button_request_cancel()

    def action_cancel_dgi(self):
        """Open wizard to cancel invoice in DGI"""
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only accounting managers can cancel invoices in DGI."))
        if self._is_dgi_anulado():
            raise UserError(
                _(
                    "This invoice has already been canceled in DGI and cannot be modified."
                )
            )
        if not self.dgi_sent:
            raise UserError(_("This invoice has not been sent to DGI yet."))
        if not self.dgi_cufe:
            raise UserError(
                _(
                    "Cannot cancel invoice: CUFE not available. The invoice may not have been successfully sent to DGI."
                )
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("Cancel Invoice in DGI"),
            "res_model": "dgi.anulacion.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id},
        }

    def button_cancel_posted_moves(self):
        """Collect the HKA motivo before requesting EDI cancellation."""
        dgi_moves = self.filtered(
            lambda move: move.dgi_sent and move._dgi_status_is("procesado")
        )
        if dgi_moves:
            if len(self) > 1:
                raise UserError(
                    _("Cancel DGI invoices one at a time so each can have its own reason.")
                )
            return self.action_cancel_dgi()
        return super().button_cancel_posted_moves()

    def button_force_cancel(self):
        for move in self:
            if move.dgi_sent and move._dgi_status_is("procesado"):
                raise UserError(
                    _(
                        "Cannot cancel: Invoice %s is processed in DGI. "
                        "Use Cancel Invoice in DGI first."
                    )
                    % move.display_name
                )
        return super().button_force_cancel()

    def button_draft(self):
        """Block reset to draft after DGI anulación, except the EDI cancel postprocess."""
        for move in self:
            if not move._is_dgi_anulado():
                continue
            if move.state == "posted" and move.edi_state == "cancelled":
                continue
            raise UserError(
                _(
                    "Cannot reset to draft: Invoice %s has been canceled in DGI and cannot be modified."
                )
                % move.display_name
            )
        return super().button_draft()

    def button_cancel(self):
        """Block cancel of a live DGI invoice; allow Odoo cancel after DGI anulación."""
        for move in self:
            if move.dgi_sent and move._dgi_status_is("procesado"):
                raise UserError(
                    _(
                        "Cannot cancel: Invoice %s is processed in DGI. "
                        "Use Cancel Invoice in DGI first."
                    )
                    % move.display_name
                )
        return super().button_cancel()

    def action_reverse(self):
        """Override to prevent creating credit note if canceled in DGI"""
        for move in self:
            if move._is_dgi_anulado():
                raise UserError(
                    _(
                        "Cannot create credit note: Invoice %s has been canceled in DGI and cannot be modified."
                    )
                    % move.display_name
                )
        return super().action_reverse()

    def _dgi_download_efactura_file(self, tipo_archivo, mimetype):
        """Fetch the CAFE PDF/XML from HKA and return a download action.

        The file is stored once per invoice and file name; repeated clicks
        refresh that attachment instead of piling up duplicates.
        """
        self.ensure_one()

        if not self.dgi_cufe:
            raise UserError(_("Cannot download e-factura: CUFE not available"))

        if not self.name:
            raise UserError(
                _("Cannot download e-factura: Document number not available")
            )

        hka_api = self.env["l10n_pa_edi.hka_api"]
        result = hka_api.descargar(
            cufe=self.dgi_cufe,
            numero_documento=self.name,
            tipo_archivo=tipo_archivo,
            move_id=self.id,
        )

        if not result["success"]:
            raise UserError(
                _("Failed to download e-factura %(type)s: %(error)s")
                % {"type": tipo_archivo, "error": result["error_message"]}
            )

        Attachment = self.env["ir.attachment"]
        values = {
            "name": result["file_name"],
            "datas": base64.b64encode(result["file_content"]),
            "res_model": "account.move",
            "res_id": self.id,
            "mimetype": mimetype,
        }
        attachment = Attachment.search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", self.id),
                ("name", "=", result["file_name"]),
            ],
            order="id desc",
            limit=1,
        )
        if attachment:
            attachment.write(values)
        else:
            attachment = Attachment.create(values)

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_download_efactura(self):
        """Download E-Factura PDF from DGI"""
        return self._dgi_download_efactura_file("PDF", "application/pdf")

    def action_download_efactura_xml(self):
        """Download E-Factura XML from DGI"""
        return self._dgi_download_efactura_file("XML", "application/xml")

    def _post(self, soft=True):
        for move in self.filtered(lambda move: move._dgi_requires_product_line_taxes()):
            move._check_dgi_product_line_taxes()
            move._check_dgi_credit_payment()
        return super()._post(soft=soft)

    def _set_next_sequence(self):
        """Override to use DGI sequence for electronic invoices."""
        self.ensure_one()

        # Check if we should use DGI sequence
        if self._should_use_dgi_sequence():
            return self._set_dgi_sequence()

        # Otherwise use standard Odoo sequence logic
        return super()._set_next_sequence()

    def _should_use_dgi_sequence(self):
        """Determine if DGI sequence should be used for this move."""
        return (
            self.journal_id.use_dgi_electronic_invoicing
            and self.journal_id.dgi_sequence_id
            and self.move_type in ("out_invoice", "out_refund")
            and self.state == "posted"
        )

    def _set_dgi_sequence(self):
        """Generate invoice name using DGI sequence."""
        self.ensure_one()
        sequence = self.journal_id.dgi_sequence_id

        if not sequence:
            raise UserError(
                _(
                    "No DGI sequence configured for journal '%(journal)s'. "
                    "Please configure one in the journal settings."
                )
                % {"journal": self.journal_id.name}
            )

        # Generate the next sequence number using the invoice date
        new_name = sequence.with_context(ir_sequence_date=self.date).next_by_id()

        if not new_name:
            raise UserError(
                _(
                    "Could not generate invoice number from DGI sequence '%(sequence)s'. "
                    "Please check the sequence configuration."
                )
                % {"sequence": sequence.name}
            )

        # Set the name
        self.name = new_name
        return True

    def action_view_hka_api_logs(self):
        """Open the API logs for this invoice."""
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only accounting managers can open HKA API logs."))
        return {
            "type": "ir.actions.act_window",
            "name": _("HKA API Logs"),
            "res_model": "hka.api.log",
            "view_mode": "list,form",
            "domain": self._hka_api_log_domain(),
            "context": {"default_move_id": self.id},
        }

