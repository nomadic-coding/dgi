# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # HKA API Log count
    hka_api_log_count = fields.Integer(
        string="API Log Count",
        compute="_compute_hka_api_log_count",
    )

    # Control credit note button visibility
    show_credit_note_button = fields.Boolean(
        string="Show Credit Note Button",
        compute="_compute_show_credit_note_button",
        default=True,
    )

    # Electronic Invoice Fields
    hka_tipo_emision = fields.Selection(
        [
            ("01", "01 - Prior Authorization, Normal"),
            ("02", "02 - Prior Authorization, Contingency"),
            ("03", "03 - Post Authorization, Normal"),
            ("04", "04 - Post Authorization, Contingency"),
        ],
        string="Emission Type",
        default="01",
    )
    hka_tipo_documento_manual = fields.Boolean(
        string="Manual Document Type",
        default=False,
        help="If checked, the document type will not be auto-computed",
    )

    hka_tipo_documento = fields.Selection(
        [
            ("01", "01 - Internal Bill"),
            ("02", "02 - Import Bill"),
            ("03", "03 - Export Bill"),
            ("04", "04 - Credit Note (E-bill)"),
            ("05", "05 - Debit Note (E-bill)"),
            ("06", "06 - Generic Credit Note"),
            ("07", "07 - Generic Debit Note"),
            ("08", "08 - Free Zone Bill"),
            ("09", "09 - Reimbursement"),
        ],
        string="Document Type",
        compute="_compute_hka_tipo_documento",
        inverse="_inverse_hka_tipo_documento",
        store=True,
        readonly=False,
        help="Type of fiscal document (computed from invoice type, can be overridden)",
    )

    @api.depends("move_type", "hka_tipo_documento_manual")
    def _compute_hka_tipo_documento(self):
        """Compute document type based on invoice type"""
        for record in self:
            if record.hka_tipo_documento_manual:
                # Don't recompute if manually set
                continue
            if record.move_type == "out_invoice":
                record.hka_tipo_documento = "01"  # Internal Bill
            elif record.move_type == "out_refund":
                if record.reversed_entry_id:
                    record.hka_tipo_documento = "04"  # Credit Note (E-bill)
                else:
                    record.hka_tipo_documento = "06"  # Credit Note (Generic)
            else:
                record.hka_tipo_documento = False

    def _inverse_hka_tipo_documento(self):
        """When manually setting the field, mark it as manual"""
        for record in self:
            if record.hka_tipo_documento:
                record.hka_tipo_documento_manual = True

    hka_naturaleza_operacion = fields.Selection(
        [
            ("01", "01 - Sale"),
            ("02", "02 - Export"),
            ("10", "10 - Transfer"),
            ("11", "11 - Return"),
            ("12", "12 - Consignment"),
            ("13", "13 - Remittance"),
            ("14", "14 - Free Delivery"),
            ("20", "20 - Purchase"),
            ("21", "21 - Import"),
        ],
        string="Nature of Operation",
        default="01",
    )
    hka_tipo_operacion = fields.Selection(
        [("1", "1 - Exit/Sale"), ("2", "2 - Entry/Purchase")],
        string="Operation Type",
        default="1",
    )
    hka_destino_operacion = fields.Selection(
        [("1", "1 - Panama"), ("2", "2 - Foreign")],
        string="Destination",
        default="1",
    )
    hka_tipo_sucursal = fields.Selection(
        [("1", "1 - Retail"), ("2", "2 - Business to Business")],
        string="Branch Type",
        default="2",
    )
    hka_formato_cafe = fields.Selection(
        [("1", "1 - No CAFE"), ("2", "2 - Ticket"), ("3", "3 - 8½x11 Paper")],
        string="CAFE Format",
        default="1",
    )
    hka_entrega_cafe = fields.Selection(
        [("1", "1 - No CAFE"), ("2", "2 - Paper"), ("3", "3 - Electronic")],
        string="CAFE Delivery",
        default="1",
    )
    hka_envio_contenedor = fields.Selection(
        [("1", "1 - Normal"), ("2", "2 - Receiver Exempts")],
        string="Container Shipping",
        default="1",
    )
    hka_proceso_generacion = fields.Selection(
        [("1", "1 - Taxpayer System")],
        string="Generation Process",
        default="1",
    )

    hka_forma_pago = fields.Selection(
        [
            ("01", "01 - Crédito (Credit)"),
            ("02", "02 - Efectivo (Cash)"),
            ("03", "03 - Tarjeta Crédito (Credit Card)"),
            ("04", "04 - Tarjeta Débito (Debit Card)"),
            ("05", "05 - Tarjeta Fidelización (Loyalty Card)"),
            ("06", "06 - Vale (Voucher)"),
            ("07", "07 - Tarjeta de Regalo (Gift Card)"),
            ("08", "08 - Transf/Depósito cta. Bancaria (Bank Transfer/Deposit)"),
            ("09", "09 - Cheque (Check)"),
            ("99", "99 - Otro (Other)"),
        ],
        string="Payment Method",
        default="08",
    )

    # DGI Response Fields
    dgi_sent = fields.Boolean(
        string="Sent to DGI", default=False, readonly=True, copy=False
    )
    dgi_sent_date = fields.Datetime(string="Sent Date", readonly=True, copy=False)
    dgi_status = fields.Char(
        string="DGI Status",
        readonly=True,
        copy=False,
        help="Status from DGI (e.g., 'procesado', 'rechazado')",
    )
    dgi_cufe = fields.Char(
        string="CUFE", readonly=True, copy=False, help="Unique Electronic Invoice Code"
    )
    dgi_qr = fields.Text(string="QR Code", readonly=True, copy=False)
    dgi_fecha_recepcion = fields.Char(
        string="DGI Reception Date", readonly=True, copy=False
    )
    dgi_protocolo_autorizacion = fields.Char(
        string="Authorization Protocol", readonly=True, copy=False
    )
    dgi_error_message = fields.Text(string="Error Message", readonly=True, copy=False)

    def _format_dgi_datetime(self, date_value):
        """
        Format date/datetime for DGI Panama in ISO 8601 format with Panama timezone

        Panama timezone: UTC-5 (no daylight saving time)
        Format: YYYY-MM-DDThh:mm:ss-05:00

        Args:
            date_value: date or datetime object

        Returns:
            str: Formatted datetime string (e.g., "2024-11-05T14:30:00-05:00")
        """
        from datetime import datetime, time

        if not date_value:
            date_value = fields.Date.today()

        # If it's a date, convert to datetime at midnight
        if not isinstance(date_value, datetime):
            date_value = datetime.combine(date_value, time.min)

        # Format: YYYY-MM-DDThh:mm:ss-05:00 (Panama is always UTC-5)
        return date_value.strftime("%Y-%m-%dT%H:%M:%S-05:00")

    def _check_mapping_codes(self):
        """Check if all mapping codes are present - collects all errors before raising"""
        self.ensure_one()

        errors = []

        # Check invoice date
        if not self.invoice_date:
            errors.append(_("Invoice date is required before sending to DGI"))

        # Check currency
        if not self.currency_id.dgi_code_id:
            errors.append(
                _("Currency DGI code is not set for currency %s")
                % self.currency_id.name
            )

        # Check partner country
        if not self.partner_id.country_id.dgi_code_id:
            errors.append(
                _("Country DGI code is not set for country %s")
                % self.partner_id.country_id.name
            )

        # Check partner DGI fields
        if self.move_type in ("out_invoice", "out_refund"):
            if not self.partner_id.dgi_tipo_cliente_fe:
                errors.append(
                    _("Partner DGI Customer Type is not set for partner %s")
                    % self.partner_id.name
                )

        # Check invoice lines exist
        if not self.invoice_line_ids:
            errors.append(
                _("Invoice must have at least one line before sending to DGI")
            )

        # Check all invoice lines for product and UOM codes
        for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
            if not line.product_id.dgi_code_id:
                errors.append(
                    _("Product DGI code is not set for product '%s' (line: %s)")
                    % (line.product_id.name or _("Unknown"), line.name or line.id)
                )
            if not line.product_uom_id.dgi_code_id:
                errors.append(
                    _("UOM DGI code is not set for UOM '%s' (line: %s)")
                    % (line.product_uom_id.name or _("Unknown"), line.name or line.id)
                )

        # Check journal configuration
        if not self.journal_id.dgi_codigo_sucursal_emisor:
            errors.append(
                _("Journal Branch Code is not configured for journal %s")
                % self.journal_id.name
            )
        if not self.journal_id.dgi_punto_facturacion_fiscal:
            errors.append(
                _("Journal Fiscal Point is not configured for journal %s")
                % self.journal_id.name
            )

        # Raise all errors at once if any found
        if errors:
            error_message = _(
                "Cannot send invoice to DGI. Please fix the following issues:\n- %s"
            ) % ("\n- ".join(errors))
            raise UserError(error_message)

    def _validate_before_send_to_dgi(self):
        """Validate invoice before sending to DGI - common validation logic"""
        self.ensure_one()

        # Validate document type matches move type
        if self.move_type == "out_invoice":
            if self.hka_tipo_documento in ("04", "06"):
                raise UserError(
                    _(
                        "Invalid document type for customer invoice: '%s' (Credit Note). "
                        "Customer invoices must use document types 01, 02, 03, 08, or 09."
                    )
                    % self.hka_tipo_documento
                )

        if not self.journal_id.use_dgi_electronic_invoicing:
            raise UserError(
                _("DGI Electronic Invoicing is not enabled for this journal")
            )

        if self.dgi_sent:
            raise UserError(_("This document has already been sent to DGI"))

        if self.state != "posted":
            raise UserError(_("Only posted invoices can be sent to DGI"))

        # Check all mapping codes and required fields
        self._check_mapping_codes()

        # Validate credit note requirements
        if self.move_type == "out_refund" and self.reversed_entry_id:
            if not self.reversed_entry_id.dgi_cufe:
                raise UserError(
                    _(
                        "Cannot send credit note: Original invoice CUFE not available. "
                        "The original invoice (%s) must be sent to DGI first before creating a credit note."
                    )
                    % self.reversed_entry_id.name
                )
            if not self.reversed_entry_id.invoice_date:
                raise UserError(
                    _(
                        "Cannot send credit note: Original invoice date is missing for invoice %s"
                    )
                    % self.reversed_entry_id.name
                )

    def _send_to_dgi_internal(self):
        """Internal method to send invoice to DGI - shared by manual and auto-send"""
        self.ensure_one()

        # Prepare and send document
        hka_api = self.env["l10n_pa_edi.hka_api"]
        document_data = self._prepare_dgi_document_data()
        result = hka_api.enviar(document_data, move_id=self.id)

        # Prepare fields to write
        fields_to_write = {
            "dgi_status": result["status"],
            "dgi_sent_date": fields.Datetime.now(),
            "dgi_error_message": result["error_message"],
            "dgi_cufe": result["dgi_cufe"],
            "dgi_qr": result["dgi_qr"],
            "dgi_fecha_recepcion": result["dgi_fecha_recepcion"],
            "dgi_protocolo_autorizacion": result["dgi_protocolo_autorizacion"],
        }

        # Only set dgi_sent = True on success
        if result["success"]:
            fields_to_write["dgi_sent"] = True

        # Write all fields at once
        self.write(fields_to_write)

        # Return result for caller to handle messaging
        return result

    def action_send_to_dgi(self):
        """Send invoice to DGI via HKA API (manual trigger)"""
        self.ensure_one()

        # Validate before sending
        self._validate_before_send_to_dgi()

        # Send to DGI
        result = self._send_to_dgi_internal()

        # Post appropriate message to chatter
        if result["success"]:
            message = (
                _("Document sent to DGI successfully. CUFE: %s") % result["dgi_cufe"]
            )
        else:
            error_message = (
                result.get("error_message")
                or result.get("mensaje")
                or _("Unknown error")
            )
            message = _("DGI Error: %s") % error_message

        self.message_post(body=message, message_type="notification")

        return True

    def _post(self, soft=True):
        """Override to automatically send invoices to DGI when posted (if enabled)"""
        res = super()._post(soft=soft)

        # Automatically send to DGI after posting for eligible invoices
        for move in self:
            # Only send if auto-send is enabled on the journal
            if (
                move.state == "posted"
                and move.move_type in ("out_invoice", "out_refund")
                and move.journal_id.use_dgi_electronic_invoicing
                and move.journal_id.dgi_auto_send_on_post
                and not move.dgi_sent
            ):
                try:
                    move._send_to_dgi_auto()
                except Exception as e:
                    # Log error but don't block posting
                    _logger.error(
                        "Failed to automatically send invoice %s to DGI: %s",
                        move.name,
                        str(e),
                        exc_info=True,
                    )
                    move.message_post(
                        body=_("Failed to automatically send to DGI: %s") % str(e),
                        message_type="notification",
                    )

        return res

    def _send_to_dgi_auto(self):
        """Internal method to send invoice to DGI (called automatically on post)"""
        self.ensure_one()

        # Quick checks before validation
        if not self.journal_id.use_dgi_electronic_invoicing:
            return  # Skip if DGI not enabled for this journal

        if self.dgi_sent:
            return  # Already sent

        if self.state != "posted":
            return  # Not posted yet

        try:
            # Validate before sending (will raise UserError if validation fails)
            self._validate_before_send_to_dgi()

            # Send to DGI
            result = self._send_to_dgi_internal()

            # Post appropriate message to chatter
            if result["success"]:
                message = _(
                    "Document automatically sent to DGI. Status: %s, CUFE: %s"
                ) % (
                    result["status"],
                    result["dgi_cufe"] or _("Pending"),
                )
                self.message_post(body=message, message_type="notification")
            else:
                error_message = (
                    result["error_message"]
                    or result.get("mensaje")
                    or _("Unknown error")
                )
                message = (
                    _("Failed to automatically send document to DGI: %s")
                    % error_message
                )
                self.message_post(body=message, message_type="notification")

        except UserError as e:
            # UserError means validation failed - log and inform user but don't block posting
            _logger.warning(
                "Validation failed for auto-send to DGI (invoice %s): %s",
                self.name,
                str(e),
            )
            self.message_post(
                body=_("Failed to automatically send to DGI: %s") % str(e),
                message_type="notification",
            )
        except Exception as e:
            # Other errors - log but don't block posting
            _logger.error(
                "Unexpected error during auto-send to DGI (invoice %s): %s",
                self.name,
                str(e),
                exc_info=True,
            )
            self.message_post(
                body=_("Failed to automatically send to DGI: %s") % str(e),
                message_type="notification",
            )

    def _is_dgi_anulado(self):
        """Check if invoice is canceled in DGI"""
        return self.dgi_status == "anulado"

    @api.depends("dgi_status")
    def _compute_show_reset_to_draft_button(self):
        """Hide reset to draft button if invoice is canceled in DGI"""
        super()._compute_show_reset_to_draft_button()
        for move in self:
            if move._is_dgi_anulado():
                move.show_reset_to_draft_button = False

    @api.depends("dgi_status", "dgi_sent", "move_type", "state")
    def _compute_show_credit_note_button(self):
        """Hide credit note button if invoice is canceled or sent to DGI"""
        for move in self:
            # Default: show button if it's a valid invoice type and posted
            move.show_credit_note_button = (
                move.move_type in ("out_invoice", "in_invoice")
                and move.state == "posted"
            )
            # Hide if canceled in DGI
            if move._is_dgi_anulado():
                move.show_credit_note_button = False

    @api.depends("dgi_status", "dgi_sent")
    def _compute_need_cancel_request(self):
        """Require cancel request when invoice is successfully sent to DGI"""
        super()._compute_need_cancel_request()
        for move in self:
            # Allow bypassing cancel request check when force_dgi_cancel context is set
            if self.env.context.get("force_dgi_cancel"):
                move.need_cancel_request = False
            # If invoice is successfully sent to DGI (procesado), require cancel request
            # This prevents direct cancellation and forces use of DGI cancellation wizard
            elif move.dgi_status == "procesado" and move.dgi_sent:
                move.need_cancel_request = True

    def _need_cancel_request(self):
        """Override to require cancel request when invoice is sent to DGI"""
        # Allow bypassing cancel request check when force_dgi_cancel context is set
        if self.env.context.get("force_dgi_cancel"):
            return False
        res = super()._need_cancel_request()
        # If invoice is successfully sent to DGI, require cancel request
        if self.dgi_status == "procesado" and self.dgi_sent:
            return True
        return res

    def button_request_cancel(self):
        """Override to open DGI cancellation wizard when invoice is sent to DGI"""
        # If invoice is sent to DGI, use DGI cancellation wizard
        if self.dgi_sent and self.dgi_status == "procesado":
            return self.action_cancel_dgi()
        return super().button_request_cancel()

    def action_cancel_dgi(self):
        """Open wizard to cancel invoice in DGI"""
        self.ensure_one()
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

    def button_draft(self):
        """Override to prevent resetting to draft if canceled in DGI"""
        for move in self:
            if move._is_dgi_anulado():
                raise UserError(
                    _(
                        "Cannot reset to draft: Invoice %s has been canceled in DGI and cannot be modified."
                    )
                    % move.display_name
                )
        return super().button_draft()

    def button_cancel(self):
        """Override to prevent canceling if already canceled in DGI"""
        # Allow cancellation if force_dgi_cancel context is set (used by DGI cancellation wizard)
        if not self.env.context.get("force_dgi_cancel"):
            for move in self:
                if move._is_dgi_anulado():
                    raise UserError(
                        _(
                            "Cannot cancel: Invoice %s has already been canceled in DGI and cannot be modified."
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

    def action_download_efactura(self):
        """Download E-Factura PDF from DGI"""
        self.ensure_one()

        if not self.dgi_cufe:
            raise UserError(_("Cannot download e-factura: CUFE not available"))

        if not self.name:
            raise UserError(
                _("Cannot download e-factura: Document number not available")
            )

        # Call HKA API to download the PDF
        hka_api = self.env["l10n_pa_edi.hka_api"]
        result = hka_api.descargar(
            cufe=self.dgi_cufe,
            numero_documento=self.name,
            tipo_archivo="PDF",
            move_id=self.id,
        )

        if result["success"]:
            # Create attachment and trigger download
            import base64

            attachment = self.env["ir.attachment"].create(
                {
                    "name": result["file_name"],
                    "datas": base64.b64encode(result["file_content"]),
                    "res_model": "account.move",
                    "res_id": self.id,
                    "mimetype": "application/pdf",
                }
            )

            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{attachment.id}?download=true",
                "target": "self",
            }
        else:
            raise UserError(
                _("Failed to download e-factura: %s") % result["error_message"]
            )

    def action_download_efactura_xml(self):
        """Download E-Factura XML from DGI"""
        self.ensure_one()

        if not self.dgi_cufe:
            raise UserError(_("Cannot download e-factura: CUFE not available"))

        if not self.name:
            raise UserError(
                _("Cannot download e-factura: Document number not available")
            )

        # Call HKA API to download the XML
        hka_api = self.env["l10n_pa_edi.hka_api"]
        result = hka_api.descargar(
            cufe=self.dgi_cufe,
            numero_documento=self.name,
            tipo_archivo="XML",
            move_id=self.id,
        )

        if result["success"]:
            # Create attachment and trigger download
            import base64

            attachment = self.env["ir.attachment"].create(
                {
                    "name": result["file_name"],
                    "datas": base64.b64encode(result["file_content"]),
                    "res_model": "account.move",
                    "res_id": self.id,
                    "mimetype": "application/xml",
                }
            )

            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{attachment.id}?download=true",
                "target": "self",
            }
        else:
            raise UserError(
                _("Failed to download e-factura XML: %s") % result["error_message"]
            )

    def _prepare_dgi_document_data(self):
        """Prepare document data for HKA API Enviar method"""
        self.ensure_one()

        # Prepare billing point (3 digits, zero-padded)
        punto_facturacion = self.journal_id.dgi_punto_facturacion_fiscal

        # Build datosTransaccion
        datos_transaccion = {
            "tipoEmision": self.hka_tipo_emision,
            "tipoDocumento": self.hka_tipo_documento,
            "numeroDocumentoFiscal": self.name,
            "puntoFacturacionFiscal": punto_facturacion,
            "fechaEmision": self._format_dgi_datetime(self.invoice_date),
            "naturalezaOperacion": self.hka_naturaleza_operacion,
            "tipoOperacion": self.hka_tipo_operacion,
            "destinoOperacion": self.hka_destino_operacion,
            "formatoCAFE": self.hka_formato_cafe,
            "entregaCAFE": self.hka_entrega_cafe,
            "envioContenedor": self.hka_envio_contenedor,
            "procesoGeneracion": self.hka_proceso_generacion,
            "tipoSucursal": self.hka_tipo_sucursal,
            "cliente": self.partner_id._prepare_dgi_cliente_data(),
            "informacionInteres": self.ref or "",
        }

        # Prepare invoice line items
        lista_items = []
        for line in self.invoice_line_ids:
            item = {
                "descripcion": line.name or line.product_id.name or "",
                "cantidad": "{:.2f}".format(line.quantity),
                "precioUnitario": "{:.2f}".format(line.price_unit),
                "precioItem": "{:.2f}".format(line.price_subtotal),
                "valorTotal": "{:.2f}".format(line.price_total),
            }
            if line.discount > 0:
                discount_amount = line.price_unit * (line.discount / 100)
                item["precioUnitarioDescuento"] = "{:.2f}".format(discount_amount)

            # Add product code if available
            if line.product_id and line.product_id.default_code:
                item["codigo"] = line.product_id.default_code

            # Add UOM if available
            item["unidadMedida"] = line.product_uom_id.dgi_code_id.code

            if line.move_id.partner_id.dgi_tipo_cliente_fe == "03":
                item["codigoCPBS"] = line.product_id.dgi_code_id.code
                item["codigoCPBSAbrev"] = line.product_id.dgi_code_id.code[:2]
                item["unidadMedidaCPBS"] = line.product_uom_id.dgi_code_id.code

            # Add tax details for this line using Odoo's computed tax information
            if line.tax_ids:
                # Prepare base line for tax computation using Odoo's official method
                base_line = self._prepare_product_base_line_for_taxes_computation(line)
                # Let Odoo compute detailed tax breakdown
                self.env["account.tax"]._add_tax_details_in_base_line(
                    base_line, self.company_id
                )

                # Extract tax amounts per tax from the computed tax_details
                for tax_data in base_line.get("tax_details", {}).get("taxes_data", []):
                    tax = tax_data.get("tax")
                    if tax and tax.hka_tax_code:
                        tax_amount = abs(tax_data.get("raw_tax_amount_currency", 0.0))

                        # Add tax information based on HKA code
                        if tax.hka_tax_code in [
                            "00",
                            "01",
                            "02",
                            "03",
                        ]:  # ITBMS variants
                            item["tasaITBMS"] = tax.hka_tax_code
                            item["valorITBMS"] = "{:.2f}".format(tax_amount)
                        elif tax.hka_tax_code == "04":  # ISC
                            item["tasaISC"] = str(tax.hka_tax_isc_id.rate)
                            item["valorISC"] = "{:.2f}".format(tax_amount)

            lista_items.append(item)

        # Calculate totals using Odoo's tax_totals (already computed by Odoo)
        total_itbms = 0.0
        total_isc = 0.0

        # tax_totals structure: {'subtotals': [{'tax_groups': [...]}]}
        # tax_totals is a Binary field that Odoo deserializes automatically as dict
        tax_totals_dict = self.tax_totals if isinstance(self.tax_totals, dict) else {}
        if tax_totals_dict:
            for subtotal in tax_totals_dict.get("subtotals", []):
                for tax_group in subtotal.get("tax_groups", []):
                    # Get all tax IDs involved in this group
                    involved_tax_ids = tax_group.get("involved_tax_ids", [])
                    tax_amount = tax_group.get("tax_amount_currency", 0.0)

                    # Map tax_ids to their HKA codes
                    for tax_id in involved_tax_ids:
                        tax = self.env["account.tax"].browse(tax_id)
                        if tax.hka_tax_code in ["00", "01", "02", "03"]:  # ITBMS
                            total_itbms += abs(tax_amount)
                        elif tax.hka_tax_code == "04":  # ISC
                            total_isc += abs(tax_amount)
                        break  # Only count once per group

        # Build totalesSubTotales
        totales_sub_totales = {
            "totalPrecioNeto": "{:.2f}".format(self.amount_untaxed),
            "totalITBMS": "{:.2f}".format(total_itbms),
            "totalMontoGravado": "{:.2f}".format(total_itbms + total_isc),
            "totalFactura": "{:.2f}".format(self.amount_total),
            "totalValorRecibido": "{:.2f}".format(self.amount_total),
            "totalTodosItems": "{:.2f}".format(self.amount_total),
            "tiempoPago": "1",  # 1=Immediate, 2=Credit
            "nroItems": str(len(lista_items)),
            "listaFormaPago": [
                {
                    "formaPagoFact": self.hka_forma_pago,
                    "valorCuotaPagada": "{:.2f}".format(self.amount_total),
                }
            ],
        }

        # Add ISC total if present
        if total_isc > 0:
            totales_sub_totales["totalISC"] = "{:.2f}".format(total_isc)

        if self.partner_id.dgi_tipo_cliente_fe == "04":
            if not self.invoice_incoterm_id.dgi_code_id:
                raise UserError(
                    _("Incoterm DGI code is not set for incoterm %s")
                    % self.invoice_incoterm_id.name
                )

            datos_transaccion["datosFacturaExportacion"] = {
                "condicionesEntrega": self.invoice_incoterm_id.dgi_code_id.code,
                "monedaOperExportacion": self.currency_id.dgi_code_id.code,
            }

        # Add referenced fiscal documents if this is a refund (credit note)
        lista_docs_fiscal_referenciados = []
        if self.move_type == "out_refund" and self.reversed_entry_id:
            original_invoice = self.reversed_entry_id

            # Validate original invoice has required data
            if not original_invoice.invoice_date:
                raise UserError(
                    _(
                        "Cannot prepare credit note: Original invoice %s is missing invoice date"
                    )
                    % original_invoice.name
                )

            doc_referenciado = {
                "fechaEmisionDocFiscalReferenciado": self._format_dgi_datetime(
                    original_invoice.invoice_date
                ),
            }
            # Add CUFE if available (electronic invoice)
            if original_invoice.dgi_cufe:
                doc_referenciado["cufeFEReferenciada"] = original_invoice.dgi_cufe

            lista_docs_fiscal_referenciados.append(doc_referenciado)

        # Add listaDocsFiscalReferenciados to datosTransaccion if present
        if lista_docs_fiscal_referenciados:
            datos_transaccion["listaDocsFiscalReferenciados"] = (
                lista_docs_fiscal_referenciados
            )

        # Build documento structure
        documento = {
            "codigoSucursalEmisor": self.journal_id.dgi_codigo_sucursal_emisor,
            "datosTransaccion": datos_transaccion,
            "listaItems": lista_items,
            "totalesSubTotales": totales_sub_totales,
        }

        return {"documento": documento}

    # Override sequence generation to use DGI sequence
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

    def _compute_hka_api_log_count(self):
        """Compute count of API logs for this invoice."""
        for move in self:
            move.hka_api_log_count = self.env["hka.api.log"].search_count(
                [("move_id", "=", move.id)]
            )

    def action_view_hka_api_logs(self):
        """Open the API logs for this invoice."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "HKA API Logs",
            "res_model": "hka.api.log",
            "view_mode": "list,form",
            "domain": [("move_id", "=", self.id)],
            "context": {"default_move_id": self.id},
        }
