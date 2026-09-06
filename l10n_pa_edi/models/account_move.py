# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.l10n_pa_edi.models.hka_combinations import (
    HKA_CONTINGENCY_EMISSION,
    HKA_DESTINO_BY_DOCUMENT,
    HKA_MOTIVO_CONTINGENCIA_MIN,
    HKA_NATURALEZA_BY_DOCUMENT,
    HKA_TIPO_OPERACION_BY_DOCUMENT,
    HKA_COMBO_WRITE_FIELDS,
    HKA_TIPO_VENTA_DOCUMENTS,
    allowed_document_types,
    allowed_entrega_cafe,
    default_destino,
)


class AccountMove(models.Model):
    _inherit = "account.move"

    hka_api_log_count = fields.Integer(
        string="API Log Count",
        compute="_compute_hka_api_log_count",
    )

    show_credit_note_button = fields.Boolean(
        string="Show Credit Note Button",
        compute="_compute_show_credit_note_button",
        default=True,
    )

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
            ("06", "06 - Generic Credit Note"),
            ("08", "08 - Free Zone Bill"),
            ("09", "09 - Reimbursement"),
            ("10", "10 - Foreign Operation Bill"),
        ],
        string="Document Type",
        compute="_compute_hka_tipo_documento",
        inverse="_inverse_hka_tipo_documento",
        store=True,
        readonly=False,
        help="Type of fiscal document (computed from invoice type, can be overridden)",
    )

    @api.depends(
        "move_type",
        "hka_tipo_documento_manual",
        "partner_id",
        "partner_id.country_id",
        "reversed_entry_id",
    )
    def _compute_hka_tipo_documento(self):
        """Compute document type from invoice type and receiver country."""
        for record in self:
            if record.hka_tipo_documento_manual:
                continue
            if record.move_type == "out_invoice":
                country_code = record.partner_id.country_id.code if record.partner_id.country_id else "PA"
                record.hka_tipo_documento = "03" if country_code and country_code != "PA" else "01"
            elif record.move_type == "out_refund":
                if record.reversed_entry_id:
                    record.hka_tipo_documento = "04"
                else:
                    record.hka_tipo_documento = "06"
            else:
                record.hka_tipo_documento = False

    def _inverse_hka_tipo_documento(self):
        """When manually setting the field, mark it as manual"""
        for record in self:
            if record.hka_tipo_documento:
                record.hka_tipo_documento_manual = True

    @api.onchange("company_id")
    def _onchange_company_hka_merge_same_dgi_code(self):
        if self.company_id:
            self.hka_merge_same_dgi_code = self.company_id.hka_merge_same_dgi_code

    @api.onchange(
        "partner_id",
        "hka_tipo_documento",
        "hka_formato_cafe",
        "hka_tipo_emision",
        "hka_forma_pago",
    )
    def _onchange_hka_compatible_fields(self):
        self._hka_apply_compatible_operation_fields()

    hka_naturaleza_operacion = fields.Selection(
        [
            ("01", "01 - Sale"),
            ("02", "02 - Export"),
            ("03", "03 - Re-export"),
            ("04", "04 - Foreign Source Sale"),
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

    hka_tipo_venta = fields.Selection(
        [
            ("1", "1 - Business Sale"),
            ("2", "2 - Fixed Asset Sale"),
            ("3", "3 - Real Estate Sale"),
            ("4", "4 - Service"),
        ],
        string="Sale Type",
        default="1",
        help="Required on sales (HKA tipoVenta). Not sent on credit or debit notes.",
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

    hka_desc_forma_pago = fields.Char(
        string="Payment Method Description",
        help="Required when Payment Method is 99 (Other).",
    )

    hka_fecha_inicio_contingencia = fields.Datetime(
        string="Contingency Start",
        help="Required when Emission Type is 02 or 04 (HKA fechaInicioContingencia).",
    )

    hka_motivo_contingencia = fields.Char(
        string="Contingency Reason",
        help="Required when Emission Type is 02 or 04. Minimum 15 characters.",
    )

    hka_allowed_document_types = fields.Char(
        compute="_compute_hka_allowed_combinations"
    )

    hka_allowed_naturalezas = fields.Char(compute="_compute_hka_allowed_combinations")

    hka_allowed_destinos = fields.Char(compute="_compute_hka_allowed_combinations")

    hka_allowed_operation_types = fields.Char(
        compute="_compute_hka_allowed_combinations"
    )

    hka_allowed_entrega_cafe = fields.Char(compute="_compute_hka_allowed_combinations")

    hka_is_sale_document = fields.Boolean(compute="_compute_hka_allowed_combinations")

    hka_requires_contingency = fields.Boolean(
        compute="_compute_hka_allowed_combinations"
    )

    # Static default: reading env.company here runs during _auto_init, before
    # res_company.hka_merge_same_dgi_code exists. create() copies the company.
    hka_merge_same_dgi_code = fields.Boolean(
        string="Merge Same DGI Code Lines",
        default=True,
        help="Group e-factura lines that share the same DGI product/service code "
        "(and the same ITBMS/ISC) into one line sent as quantity 1 with the "
        "net total as unit price. Defaults from the company setting.",
    )

    hka_motivo_anulacion = fields.Text(
        string="DGI Cancellation Reason",
        copy=False,
        help="Reason sent to HKA Anulación. Written by the cancellation wizard.",
    )

    dgi_sent = fields.Boolean(
        string="Sent to DGI",
        compute="_compute_dgi_sent",
        store=True,
        readonly=True,
        copy=False,
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

    _DGI_API_FIELDS = frozenset({
        "dgi_sent",
        "dgi_sent_date",
        "dgi_status",
        "dgi_cufe",
        "dgi_qr",
        "dgi_fecha_recepcion",
        "dgi_protocolo_autorizacion",
        "dgi_error_message",
    })

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS account_move_company_dgi_cufe_uniq
            ON account_move (company_id, dgi_cufe)
            WHERE dgi_cufe IS NOT NULL AND dgi_cufe != ''
            """
        )

    @api.depends("edi_state", "dgi_status", "dgi_cufe")
    def _compute_dgi_sent(self):
        for move in self:
            accepted = (
                move.edi_state in ("sent", "to_cancel", "cancelled")
                or move.dgi_status in ("procesado", "anulado")
            )
            move.dgi_sent = bool(move.dgi_cufe) and accepted

    @api.depends(
        "move_type",
        "partner_id",
        "partner_id.country_id",
        "hka_tipo_documento",
        "hka_formato_cafe",
        "hka_tipo_emision",
    )
    def _compute_hka_allowed_combinations(self):
        for record in self:
            country_code = (
                record.partner_id.country_id.code if record.partner_id.country_id else None
            )
            record.hka_allowed_document_types = ",".join(
                allowed_document_types(record.move_type, country_code)
            )
            record.hka_allowed_naturalezas = ",".join(
                HKA_NATURALEZA_BY_DOCUMENT.get(record.hka_tipo_documento, ())
            )
            record.hka_allowed_destinos = ",".join(
                HKA_DESTINO_BY_DOCUMENT.get(record.hka_tipo_documento, ())
            )
            record.hka_allowed_operation_types = ",".join(
                HKA_TIPO_OPERACION_BY_DOCUMENT.get(record.hka_tipo_documento, ())
            )
            record.hka_allowed_entrega_cafe = ",".join(
                allowed_entrega_cafe(record.hka_formato_cafe)
            )
            record.hka_is_sale_document = (
                record.hka_tipo_documento in HKA_TIPO_VENTA_DOCUMENTS
            )
            record.hka_requires_contingency = (
                record.hka_tipo_emision in HKA_CONTINGENCY_EMISSION
            )

    def _hka_partner_country_code(self):
        self.ensure_one()
        return self.partner_id.country_id.code if self.partner_id.country_id else None

    def _hka_compatible_operation_vals(self):
        """Values that bring HKA transaction fields back to a valid combination."""
        self.ensure_one()
        if self.move_type not in ("out_invoice", "out_refund"):
            return {}
        vals = {}
        country_code = self._hka_partner_country_code()
        allowed_docs = allowed_document_types(self.move_type, country_code)
        tipo = self.hka_tipo_documento
        if allowed_docs and tipo not in allowed_docs:
            tipo = allowed_docs[0]
            vals["hka_tipo_documento"] = tipo
            vals["hka_tipo_documento_manual"] = True
        naturalezas = HKA_NATURALEZA_BY_DOCUMENT.get(tipo, ())
        if naturalezas and self.hka_naturaleza_operacion not in naturalezas:
            vals["hka_naturaleza_operacion"] = naturalezas[0]
        destinos = HKA_DESTINO_BY_DOCUMENT.get(tipo, ())
        if destinos:
            preferred = default_destino(destinos, country_code)
            if self.hka_destino_operacion not in destinos:
                vals["hka_destino_operacion"] = preferred
            elif country_code == "PA" and self.hka_destino_operacion == "2" and "1" in destinos:
                vals["hka_destino_operacion"] = "1"
            elif (
                country_code
                and country_code != "PA"
                and self.hka_destino_operacion == "1"
                and "2" in destinos
            ):
                vals["hka_destino_operacion"] = "2"
        operations = HKA_TIPO_OPERACION_BY_DOCUMENT.get(tipo, ())
        if operations and self.hka_tipo_operacion not in operations:
            vals["hka_tipo_operacion"] = operations[0]
        if tipo in HKA_TIPO_VENTA_DOCUMENTS:
            if not self.hka_tipo_venta:
                vals["hka_tipo_venta"] = "1"
        elif self.hka_tipo_venta:
            vals["hka_tipo_venta"] = False
        entregas = allowed_entrega_cafe(self.hka_formato_cafe)
        if entregas and self.hka_entrega_cafe not in entregas:
            vals["hka_entrega_cafe"] = entregas[0]
        if self.hka_tipo_emision not in HKA_CONTINGENCY_EMISSION:
            if self.hka_fecha_inicio_contingencia:
                vals["hka_fecha_inicio_contingencia"] = False
            if self.hka_motivo_contingencia:
                vals["hka_motivo_contingencia"] = False
        if self.hka_forma_pago != "99" and self.hka_desc_forma_pago:
            vals["hka_desc_forma_pago"] = False
        return vals

    def _hka_apply_compatible_operation_fields(self):
        for record in self:
            updates = record._hka_compatible_operation_vals()
            if updates:
                record.update(updates)

    def _hka_preview_combo_record(self, vals):
        self.ensure_one()
        defaults = {
            "move_type": self.move_type,
            "partner_id": self.partner_id.id,
            "journal_id": self.journal_id.id,
            "hka_tipo_documento": self.hka_tipo_documento,
            "hka_naturaleza_operacion": self.hka_naturaleza_operacion,
            "hka_destino_operacion": self.hka_destino_operacion,
            "hka_tipo_operacion": self.hka_tipo_operacion,
            "hka_tipo_venta": self.hka_tipo_venta,
            "hka_formato_cafe": self.hka_formato_cafe,
            "hka_entrega_cafe": self.hka_entrega_cafe,
            "hka_tipo_emision": self.hka_tipo_emision,
            "hka_fecha_inicio_contingencia": self.hka_fecha_inicio_contingencia,
            "hka_motivo_contingencia": self.hka_motivo_contingencia,
            "hka_forma_pago": self.hka_forma_pago,
            "hka_desc_forma_pago": self.hka_desc_forma_pago,
            "hka_tipo_documento_manual": self.hka_tipo_documento_manual,
        }
        defaults.update({key: vals[key] for key in defaults if key in vals})
        return self.new(defaults)

    @api.model_create_multi
    def create(self, vals_list):
        cleaned = []
        for vals in vals_list:
            vals = {key: value for key, value in vals.items() if key not in self._DGI_API_FIELDS}
            if "hka_merge_same_dgi_code" not in vals:
                company = self.env["res.company"].browse(
                    vals.get("company_id") or self.env.company.id
                )
                vals["hka_merge_same_dgi_code"] = company.hka_merge_same_dgi_code
            move_type = vals.get("move_type") or self.env.context.get(
                "default_move_type"
            )
            if move_type in ("out_invoice", "out_refund"):
                preview = self.new(vals)
                vals.update(preview._hka_compatible_operation_vals())
            cleaned.append(vals)
        return super().create(cleaned)

    def write(self, vals):
        if any(field in vals for field in self._DGI_API_FIELDS):
            vals = {key: value for key, value in vals.items() if key not in self._DGI_API_FIELDS}
            if not vals:
                return True
        if not (HKA_COMBO_WRITE_FIELDS & set(vals)):
            return super().write(vals)
        if len(self) > 1:
            for record in self:
                record.write(vals)
            return True
        preview = self._hka_preview_combo_record(vals)
        vals = dict(vals)
        vals.update(preview._hka_compatible_operation_vals())
        return super().write(vals)

    @api.constrains(
        "move_type",
        "partner_id",
        "hka_tipo_documento",
        "hka_naturaleza_operacion",
        "hka_destino_operacion",
        "hka_tipo_operacion",
        "hka_tipo_venta",
        "hka_formato_cafe",
        "hka_entrega_cafe",
        "hka_tipo_emision",
        "hka_fecha_inicio_contingencia",
        "hka_motivo_contingencia",
        "hka_forma_pago",
        "hka_desc_forma_pago",
    )
    def _check_hka_field_combinations(self):
        for record in self:
            if record.move_type not in ("out_invoice", "out_refund"):
                continue
            if not record.journal_id.use_dgi_electronic_invoicing:
                continue
            errors = record._hka_combination_errors()
            if errors:
                raise ValidationError("\n".join(errors))

    def _hka_combination_errors(self):
        self.ensure_one()
        errors = []
        country_code = self._hka_partner_country_code()
        allowed_docs = allowed_document_types(self.move_type, country_code)
        tipo = self.hka_tipo_documento
        if allowed_docs and tipo and tipo not in allowed_docs:
            errors.append(
                _("Document Type %(doc)s is not valid for this invoice and receiver.")
                % {"doc": tipo}
            )
        naturalezas = HKA_NATURALEZA_BY_DOCUMENT.get(tipo, ())
        if naturalezas and self.hka_naturaleza_operacion not in naturalezas:
            errors.append(
                _(
                    "Nature of Operation %(nature)s is not valid for Document Type %(doc)s."
                )
                % {"nature": self.hka_naturaleza_operacion, "doc": tipo}
            )
        destinos = HKA_DESTINO_BY_DOCUMENT.get(tipo, ())
        if destinos and self.hka_destino_operacion not in destinos:
            errors.append(
                _("Destination %(dest)s is not valid for Document Type %(doc)s.")
                % {"dest": self.hka_destino_operacion, "doc": tipo}
            )
        operations = HKA_TIPO_OPERACION_BY_DOCUMENT.get(tipo, ())
        if operations and self.hka_tipo_operacion not in operations:
            errors.append(
                _("Operation Type %(op)s is not valid for Document Type %(doc)s.")
                % {"op": self.hka_tipo_operacion, "doc": tipo}
            )
        if tipo in HKA_TIPO_VENTA_DOCUMENTS and not self.hka_tipo_venta:
            errors.append(_("Sale Type is required for sales documents."))
        if tipo not in HKA_TIPO_VENTA_DOCUMENTS and self.hka_tipo_venta:
            errors.append(_("Sale Type must be empty when the document is not a sale."))
        entregas = allowed_entrega_cafe(self.hka_formato_cafe)
        if entregas and self.hka_entrega_cafe not in entregas:
            errors.append(
                _("CAFE Delivery %(delivery)s is not valid for CAFE Format %(fmt)s.")
                % {"delivery": self.hka_entrega_cafe, "fmt": self.hka_formato_cafe}
            )
        if self.hka_tipo_emision in HKA_CONTINGENCY_EMISSION:
            if not self.hka_fecha_inicio_contingencia:
                errors.append(
                    _("Contingency Start is required when Emission Type is 02 or 04.")
                )
            motivo = (self.hka_motivo_contingencia or "").strip()
            if len(motivo) < HKA_MOTIVO_CONTINGENCIA_MIN:
                errors.append(
                    _(
                        "Contingency Reason must be at least %(min)s characters "
                        "when Emission Type is 02 or 04."
                    )
                    % {"min": HKA_MOTIVO_CONTINGENCIA_MIN}
                )
        if self.hka_forma_pago == "99" and not (self.hka_desc_forma_pago or "").strip():
            errors.append(
                _("Payment Method Description is required when Payment Method is 99.")
            )
        pais = ""
        if self.partner_id.country_id and self.partner_id.country_id.dgi_code_id:
            pais = self.partner_id.country_id.dgi_code_id.code or ""
        elif self.partner_id.country_id:
            pais = "ZZ"
        if self.hka_destino_operacion == "1" and pais and pais != "PA":
            errors.append(
                _("Destination Panama requires a receiver country code PA, not %s.")
                % pais
            )
        if self.hka_destino_operacion == "2" and pais == "PA":
            errors.append(_("Destination Foreign cannot be used when the receiver country is PA."))
        return errors

    @api.private
    def _dgi_write_api_fields(self, vals):
        """Write DGI response fields. Not RPC-callable."""
        return super().write(vals)

    def _dgi_commit_api_fields(self, vals):
        """Write DGI response fields on this cursor.

        A second connection must not UPDATE this invoice while Enviar still
        holds the EDI / HKA-log locks; that deadlocks Process now. If the
        current transaction later rolls back after HKA already accepted the
        document, a retry gets code 102 with the CUFE and is treated as sent.
        """
        self.ensure_one()
        self._dgi_write_api_fields(vals)

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
        """Hide the credit note button only after the invoice is canceled in DGI."""
        for move in self:
            move.show_credit_note_button = (
                move.move_type in ("out_invoice", "in_invoice")
                and move.state == "posted"
            )
            if move._is_dgi_anulado():
                move.show_credit_note_button = False

    @api.depends("dgi_status", "dgi_sent")
    def _compute_need_cancel_request(self):
        """Require the DGI wizard while the invoice is still procesado in DGI."""
        super()._compute_need_cancel_request()
        for move in self:
            if move.dgi_status == "anulado":
                move.need_cancel_request = False
            elif move.dgi_status == "procesado" and move.dgi_sent:
                move.need_cancel_request = True

    def _compute_hka_api_log_count(self):
        """Compute count of API logs for this invoice."""
        for move in self:
            move.hka_api_log_count = self.env["hka.api.log"].search_count(
                [("move_id", "=", move.id)]
            )

