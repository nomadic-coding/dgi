# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.modules.registry import Registry
from odoo.tools.float_utils import float_compare
from odoo.tools.mail import html2plaintext

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

_logger = logging.getLogger(__name__)

HKA_ITBMS_RATES = {
    "00": 0.0,
    "01": 0.07,
    "02": 0.10,
    "03": 0.15,
}


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
    hka_merge_same_dgi_code = fields.Boolean(
        string="Merge Same DGI Code Lines",
        default=lambda self: self.env.company.hka_merge_same_dgi_code,
        help="Group e-factura lines that share the same DGI product/service code "
        "(and the same ITBMS/ISC) into one line. Defaults from the company setting.",
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
        """Write DGI fields now, and commit them on a second cursor when the move is already in DB.

        That keeps CUFE / anulado after an HKA success if the current transaction later
        rolls back. Uncommitted test records are only visible on this cursor.
        """
        self.ensure_one()
        self._dgi_write_api_fields(vals)
        try:
            with self.env.registry.cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                move = env["account.move"].browse(self.id)
                if not move.exists():
                    return
                move._dgi_write_api_fields(vals)
                cr.commit()
        except Exception:
            _logger.exception(
                "Could not persist DGI fields on a separate cursor for move %s",
                self.id,
            )

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

    def _prepare_dgi_informacion_interes(self):
        """Plain text for HKA (narration is HTML); line breaks as U+2028 LINE SEPARATOR."""
        self.ensure_one()
        line_sep = "\u2028"
        parts = []
        ref = (self.ref or "").strip()
        narration = (self.narration or "").strip()
        if ref:
            parts.append("Customer Reference: " + html2plaintext(ref).strip())
        if narration:
            marked = (
                narration.replace("</p>", "</p>\n")
                .replace("<br>", "\n")
                .replace("<br/>", "\n")
                .replace("<br />", "\n")
            )
            parts.append(html2plaintext(marked).strip())
        if not parts:
            return ""
        plain = "\n\n".join(p for p in parts if p)
        plain = plain.replace("\r\n", "\n").replace("\r", "\n")
        plain = plain.replace("\n", line_sep)
        return plain.strip()[:5000]

    def _hka_normalize_lista_item_descripcion(self, raw, max_len=500, truncate=True):
        """Description text for listaItems; newlines -> U+2028 (invoice line names are plain)."""
        if not raw:
            return ""
        plain = str(raw).strip()
        if not plain:
            return ""
        plain = plain.replace("\r\n", "\n").replace("\r", "\n")
        plain = plain.replace("\n", "\u2028")
        if truncate and max_len:
            return plain[:max_len]
        return plain

    def _hka_itbms_amount_from_base(self, precio_item, tasa):
        """HKA validates valorITBMS against precioItem * official ITBMS rate."""
        rate = HKA_ITBMS_RATES.get(tasa or "00", 0.0)
        return self.currency_id.round(float(precio_item) * rate)

    def _hka_sync_item_valor_total(self, item):
        """valorTotal must match precioItem + valorITBMS + valorISC (HKA)."""
        base = float(item["precioItem"])
        itbms = float(item.get("valorITBMS") or 0)
        isc = float(item.get("valorISC") or 0)
        item["valorTotal"] = "{:.2f}".format(self.currency_id.round(base + itbms + isc))

    def _hka_parse_tax_totals_for_hka(self, tax_totals_dict):
        """Read Odoo tax_totals: merge groups by ITBMS tasa (00–03) / ISC rate, signed amounts.

        ITBMS: merged by tasa. ISC (04): merged by ``hka_tax_isc_id.rate`` (same tasaISC on HKA),
        so multiple taxes pointing at the same rate share one consolidated row.
        """
        self.ensure_one()
        itbms_acc = defaultdict(lambda: [0.0, 0.0])  # base, tax
        isc_acc = defaultdict(lambda: [0.0, 0.0])
        unmapped = []

        if not isinstance(tax_totals_dict, dict) or not tax_totals_dict:
            return {
                "itbms_rows": [],
                "isc_rows": [],
                "total_itbms": 0.0,
                "total_isc": 0.0,
            }

        for subtotal in tax_totals_dict.get("subtotals") or []:
            for tg in subtotal.get("tax_groups") or []:
                involved = tg.get("involved_tax_ids") or []
                base = float(tg.get("base_amount_currency") or 0.0)
                tax_amt = float(tg.get("tax_amount_currency") or 0.0)
                if self.currency_id.is_zero(base) and self.currency_id.is_zero(tax_amt):
                    continue

                tax = None
                for tid in involved:
                    t = self.env["account.tax"].browse(tid)
                    if t and t.exists() and t.hka_tax_code:
                        tax = t
                        break

                if not tax:
                    label = (
                        tg.get("group_name")
                        or tg.get("tax_group_name")
                        or _("Unknown tax group")
                    )
                    unmapped.append(
                        _(
                            "Tax group '%(label)s' has no tax with an HKA code "
                            "(base=%(base).2f, tax=%(tax).2f)"
                        )
                        % {"label": label, "base": base, "tax": tax_amt}
                    )
                    continue

                code = tax.hka_tax_code
                if code in ("00", "01", "02", "03"):
                    itbms_acc[code][0] += base
                    itbms_acc[code][1] += tax_amt
                elif code == "04":
                    if not tax.hka_tax_isc_id:
                        unmapped.append(
                            _("ISC tax '%s' is missing HKA ISC rate configuration")
                            % tax.display_name
                        )
                        continue
                    base_isc = float(tg.get("base_amount_currency") or 0.0)
                    if self.currency_id.is_zero(base_isc):
                        disp_base = tg.get("display_base_amount_currency")
                        if disp_base is not False and disp_base is not None:
                            base_isc = float(disp_base or 0.0)
                    rate_key = round(float(tax.hka_tax_isc_id.rate), 6)
                    isc_acc[rate_key][0] += base_isc
                    isc_acc[rate_key][1] += tax_amt
                else:
                    unmapped.append(
                        _("Tax '%s' uses unsupported HKA code '%s'")
                        % (tax.display_name, code)
                    )

        if unmapped:
            raise UserError(
                _("Cannot build HKA payload — fix tax mapping:\n%s")
                % "\n".join("- %s" % m for m in unmapped)
            )

        itbms_rows = [
            (
                tasa,
                self.currency_id.round(pair[0]),
                self.currency_id.round(pair[1]),
            )
            for tasa, pair in sorted(itbms_acc.items())
        ]

        isc_rows = [
            (
                rate_key,
                self.currency_id.round(pair[0]),
                self.currency_id.round(pair[1]),
            )
            for rate_key, pair in sorted(isc_acc.items(), key=lambda kv: kv[0])
        ]

        total_itbms = self.currency_id.round(sum(t for _, _, t in itbms_rows))
        total_isc = self.currency_id.round(sum(t for _, _, t in isc_rows))

        return {
            "itbms_rows": itbms_rows,
            "isc_rows": isc_rows,
            "total_itbms": total_itbms,
            "total_isc": total_isc,
        }

    def _hka_validate_consolidated_items(self, items, tax_parsed):
        """Ensure consolidated listaItems match the move after rounding adjustments."""
        self.ensure_one()
        if not items:
            raise UserError(
                _("Cannot send to DGI: consolidated invoice has no line items.")
            )

        cur = self.currency_id
        rnd = cur.rounding or 0.01

        sum_b = cur.round(sum(float(x["precioItem"]) for x in items))
        sum_ib = cur.round(sum(float(x.get("valorITBMS") or 0) for x in items))
        sum_isc = cur.round(sum(float(x.get("valorISC") or 0) for x in items))
        sum_tot = cur.round(sum(float(x["valorTotal"]) for x in items))

        if self.move_type == "out_invoice":
            for it in items:
                b = float(it["precioItem"])
                if float_compare(b, 0.0, precision_rounding=rnd) < 0:
                    raise UserError(
                        _(
                            "Cannot send this customer invoice to DGI: consolidated detail has "
                            "negative net amount (%(amt).2f). Check down payment / tax lines."
                        )
                        % {"amt": b}
                    )

        checks = [
            (sum_b, self.amount_untaxed, _("untaxed total")),
            (sum_ib, tax_parsed["total_itbms"], _("ITBMS")),
            (sum_isc, tax_parsed["total_isc"], _("ISC")),
            (sum_tot, self.amount_total, _("total with tax")),
        ]
        for a, b, label in checks:
            if float_compare(a, b, precision_rounding=rnd) != 0:
                raise UserError(
                    _(
                        "HKA consolidated payload does not match invoice %(label)s: "
                        "payload=%(a).2f, move=%(b).2f"
                    )
                    % {"label": label, "a": a, "b": b}
                )

    def _hka_itbms_net_per_tasa_from_lines(self, product_lines):
        """Signed net ITBMS per HKA tasa (00–03) across all product lines (+ and - qty)."""
        self.ensure_one()
        per_tasa = defaultdict(float)
        for line in product_lines:
            if not line.tax_ids:
                continue
            base_line = self._prepare_product_base_line_for_taxes_computation(line)
            self.env["account.tax"]._add_tax_details_in_base_line(
                base_line, self.company_id
            )
            for tax_data in base_line.get("tax_details", {}).get("taxes_data", []):
                tax = tax_data.get("tax")
                if tax and tax.hka_tax_code in ("00", "01", "02", "03"):
                    per_tasa[tax.hka_tax_code] += tax_data.get(
                        "raw_tax_amount_currency", 0.0
                    )
        return dict(per_tasa)

    def _hka_reconcile_lista_items_itbms(
        self, lista_items, product_lines, total_itbms_invoice
    ):
        """Per tasaITBMS: spread valorITBMS so each group matches net ITBMS on the move."""
        self.ensure_one()
        net_per_tasa = self._hka_itbms_net_per_tasa_from_lines(product_lines)
        by_tasa = defaultdict(list)
        for it in lista_items:
            if "valorITBMS" in it and "tasaITBMS" in it:
                by_tasa[it["tasaITBMS"]].append(it)

        for tasa, items_g in by_tasa.items():
            target = self.currency_id.round(net_per_tasa.get(tasa, 0.0))
            sum_g = sum(float(it["valorITBMS"]) for it in items_g)
            if abs(self.currency_id.round(sum_g - target)) <= 0.005:
                for it in items_g:
                    self._hka_sync_item_valor_total(it)
                continue
            if abs(target) <= 0.005:
                for it in items_g:
                    it["valorITBMS"] = "{:.2f}".format(0.0)
                    self._hka_sync_item_valor_total(it)
                continue
            if sum_g <= 0:
                for it in items_g:
                    self._hka_sync_item_valor_total(it)
                continue
            acc = 0.0
            for idx, it in enumerate(items_g):
                t = float(it["valorITBMS"])
                if idx == len(items_g) - 1:
                    v = self.currency_id.round(target - acc)
                else:
                    v = self.currency_id.round(t * target / sum_g)
                    acc += v
                it["valorITBMS"] = "{:.2f}".format(v)
            for it in items_g:
                self._hka_sync_item_valor_total(it)

        # Rounding drift vs tax_totals total ITBMS (e.g. multiple tasas)
        items_with = [it for it in lista_items if "valorITBMS" in it]
        if not items_with:
            return
        sum_lines = sum(float(it["valorITBMS"]) for it in items_with)
        rem = self.currency_id.round(sum_lines - total_itbms_invoice)
        if abs(rem) > 0.005:
            last = items_with[-1]
            last["valorITBMS"] = "{:.2f}".format(
                self.currency_id.round(float(last["valorITBMS"]) - rem)
            )
            self._hka_sync_item_valor_total(last)

    def _hka_itbms_tasa_for_line(self, line):
        """First ITBMS HKA tasa (00–03) on the line's taxes; default 00 if none."""
        self.ensure_one()
        for tax in line.tax_ids:
            if tax.hka_tax_code in ("00", "01", "02", "03"):
                return tax.hka_tax_code
        return "00"

    def _hka_group_item_lines_by_itbms_tasa(self, item_lines):
        """Positive product lines bucketed by their ITBMS HKA code."""
        buckets = defaultdict(lambda: self.env["account.move.line"])
        for line in item_lines:
            tasa = self._hka_itbms_tasa_for_line(line)
            buckets[tasa] |= line
        return buckets

    def _hka_group_item_lines_by_isc_rate(self, item_lines):
        """Positive lines that carry ISC (04), keyed by rounded ``hka_tax_isc_id.rate`` (tasaISC)."""
        buckets = defaultdict(lambda: self.env["account.move.line"])
        for line in item_lines:
            for tax in line.tax_ids:
                if tax.hka_tax_code == "04" and tax.hka_tax_isc_id:
                    rate_key = round(float(tax.hka_tax_isc_id.rate), 6)
                    buckets[rate_key] |= line
                    break
        return buckets

    def _hka_isc_base_per_rate_from_lines(self, product_lines):
        """Per rounded tasaISC: sum of Odoo ISC bases (``raw_base_amount_currency``) on product lines."""
        self.ensure_one()
        per_rate = defaultdict(float)
        for line in product_lines:
            if not line.tax_ids:
                continue
            base_line = self._prepare_product_base_line_for_taxes_computation(line)
            self.env["account.tax"]._add_tax_details_in_base_line(
                base_line, self.company_id
            )
            for tax_data in base_line.get("tax_details", {}).get("taxes_data", []):
                tax = tax_data.get("tax")
                if tax and tax.hka_tax_code == "04" and tax.hka_tax_isc_id:
                    rate_key = round(float(tax.hka_tax_isc_id.rate), 6)
                    per_rate[rate_key] += float(
                        tax_data.get("raw_base_amount_currency") or 0.0
                    )
        return dict(per_rate)

    def _hka_join_descriptions_for_lines(self, lines, fallback):
        """U+2028-joined line names for listaItems descripcion (max 500)."""
        self.ensure_one()
        name_chunks = []
        for n in lines.mapped("name"):
            if not n:
                continue
            t = self._hka_normalize_lista_item_descripcion(n, truncate=False)
            if t:
                name_chunks.append(t)
        if name_chunks:
            return "\u2028".join(name_chunks)[:500]
        return self._hka_normalize_lista_item_descripcion(fallback)

    def _hka_cpbs_fields(self, product, uom_code):
        """CPBS fields for government receivers. Requires a mapped product DGI code."""
        self.ensure_one()
        if self.partner_id.dgi_tipo_cliente_fe != "03":
            return {}
        if not product or not product.dgi_code_id or not product.dgi_code_id.code:
            raise UserError(
                _(
                    "Product DGI/CPBS code is required when the receiver is a "
                    "government entity (%s)."
                )
                % (product.display_name if product else _("Unknown product"))
            )
        code = product.dgi_code_id.code
        return {
            "codigoCPBS": code,
            "codigoCPBSAbrev": code[:2],
            "unidadMedidaCPBS": uom_code,
        }

    def _hka_prepare_consolidated_invoice_items(self, item_lines, tax_parsed):
        """Build listaItems: one row per merged ITBMS tasa / ISC rate (net of all lines).

        Product descriptions are grouped by HKA tax: each row lists only lines sharing
        that ITBMS tasa or the same ISC ``tasaISC`` (rate).

        ``tax_parsed`` is returned by :meth:`_hka_parse_tax_totals_for_hka`."""
        self.ensure_one()
        default_ref = item_lines[0]
        names_all_fallback = (
            default_ref.name or default_ref.product_id.name or _("Invoice")
        )
        names_desc_all = self._hka_join_descriptions_for_lines(
            item_lines, names_all_fallback
        )

        itbms_line_buckets = self._hka_group_item_lines_by_itbms_tasa(item_lines)
        isc_line_buckets = self._hka_group_item_lines_by_isc_rate(item_lines)
        isc_base_from_lines = self._hka_isc_base_per_rate_from_lines(item_lines)

        def base_item_dict(ref_line):
            uom = ref_line.product_uom_id.dgi_code_id.code or "und"
            it = {
                "cantidad": "1.00",
                "unidadMedida": uom,
            }
            if ref_line.product_id and ref_line.product_id.default_code:
                it["codigo"] = ref_line.product_id.default_code
            it.update(self._hka_cpbs_fields(ref_line.product_id, uom))
            return it

        itbms_rows = list(tax_parsed["itbms_rows"])
        isc_rows = list(tax_parsed["isc_rows"])
        total_itbms = tax_parsed["total_itbms"]
        total_isc = tax_parsed["total_isc"]

        isc_carry_net_only = (
            not itbms_rows
            and isc_rows
            and self.currency_id.is_zero(total_itbms)
            and not self.currency_id.is_zero(self.amount_untaxed)
        )
        if not itbms_rows and not self.currency_id.is_zero(self.amount_untaxed):
            if not isc_carry_net_only:
                b0 = self.currency_id.round(self.amount_untaxed)
                itbms_rows = [("00", b0, 0.0)]
                total_itbms = 0.0

        items = []
        for tasa, base_raw, tax_raw in itbms_rows:
            lines_t = itbms_line_buckets.get(tasa, self.env["account.move.line"])
            ref_line = lines_t[:1] or default_ref
            fallback_lbl = "%s — %s" % (names_all_fallback, _("ITBMS %s") % tasa)
            desc = self._hka_join_descriptions_for_lines(lines_t, fallback_lbl).strip()
            if not desc:
                desc = (names_desc_all or (_("ITBMS %s") % tasa))[:500]
            it = base_item_dict(ref_line)
            it["descripcion"] = desc[:500]
            b = self.currency_id.round(base_raw)
            tx = self.currency_id.round(tax_raw)
            it["precioUnitario"] = "{:.2f}".format(b)
            it["precioItem"] = "{:.2f}".format(b)
            it["tasaITBMS"] = tasa
            it["valorITBMS"] = "{:.2f}".format(tx)
            it["valorTotal"] = "{:.2f}".format(self.currency_id.round(b + tx))
            items.append(it)

        for rate_key, base_raw, isc_raw in isc_rows:
            rate_str = str(rate_key)
            lines_r = isc_line_buckets.get(rate_key, self.env["account.move.line"])
            ref_line = lines_r[:1] or default_ref
            isc_lbl = _("ISC %s") % rate_str
            fallback_lbl = "%s — %s" % (names_all_fallback, isc_lbl)
            desc = self._hka_join_descriptions_for_lines(lines_r, fallback_lbl).strip()
            if not desc:
                desc = (names_desc_all or isc_lbl)[:500]
            it = base_item_dict(ref_line)
            it["descripcion"] = desc[:500]
            b = self.currency_id.round(base_raw)
            if (
                isc_carry_net_only
                and self.currency_id.is_zero(b)
            ):
                bline = isc_base_from_lines.get(rate_key)
                if bline and not self.currency_id.is_zero(bline):
                    b = self.currency_id.round(bline)
            isc_amt = self.currency_id.round(isc_raw)
            it["precioUnitario"] = "{:.2f}".format(b)
            it["precioItem"] = "{:.2f}".format(b)
            it["tasaITBMS"] = "00"
            it["valorITBMS"] = "{:.2f}".format(0.0)
            it["tasaISC"] = rate_str
            it["valorISC"] = "{:.2f}".format(isc_amt)
            it["valorTotal"] = "{:.2f}".format(self.currency_id.round(b + isc_amt))
            items.append(it)

        if not items:
            it = base_item_dict(default_ref)
            it["descripcion"] = names_desc_all
            b = self.currency_id.round(self.amount_untaxed)
            t = self.currency_id.round(total_itbms)
            it["precioUnitario"] = it["precioItem"] = "{:.2f}".format(b)
            it["tasaITBMS"] = "00"
            it["valorITBMS"] = "{:.2f}".format(t)
            it["valorTotal"] = "{:.2f}".format(self.currency_id.round(b + t))
            items.append(it)

        sum_b = sum(float(x["precioItem"]) for x in items)
        sum_ib = sum(float(x.get("valorITBMS") or 0) for x in items)
        sum_isc = sum(float(x.get("valorISC") or 0) for x in items)
        db = self.currency_id.round(self.amount_untaxed - sum_b)
        dit = self.currency_id.round(total_itbms - sum_ib)
        dis = self.currency_id.round(total_isc - sum_isc)
        if items and (
            not self.currency_id.is_zero(db)
            or not self.currency_id.is_zero(dit)
            or not self.currency_id.is_zero(dis)
        ):
            _logger.debug(
                "HKA consolidated drift adjustment move=%s db=%s dit=%s dis=%s",
                self.id,
                db,
                dit,
                dis,
            )
            last = items[-1]
            b = self.currency_id.round(float(last["precioItem"]) + db)
            last["precioUnitario"] = last["precioItem"] = "{:.2f}".format(b)
            if "valorITBMS" in last:
                vi = self.currency_id.round(float(last["valorITBMS"]) + dit)
                last["valorITBMS"] = "{:.2f}".format(vi)
            if "valorISC" in last:
                vs = self.currency_id.round(float(last["valorISC"]) + dis)
                last["valorISC"] = "{:.2f}".format(vs)
            last["valorTotal"] = "{:.2f}".format(
                self.currency_id.round(
                    float(last["precioItem"])
                    + float(last.get("valorITBMS") or 0)
                    + float(last.get("valorISC") or 0)
                )
            )

        self._hka_validate_consolidated_items(items, tax_parsed)
        return items

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
        for line in self.invoice_line_ids.filtered(
            lambda l: l.display_type == "product" and l.product_uom_id
        ):
            if (
                self.partner_id.dgi_tipo_cliente_fe == "03"
                and not line.product_id.dgi_code_id
            ):
                errors.append(
                    _(
                        "Product DGI/CPBS code is not set for product '%s' (line: %s). "
                        "Required for government receivers."
                    )
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
        elif self.journal_id.dgi_punto_facturacion_fiscal == "000":
            errors.append(_("Journal Fiscal Point cannot be 000"))

        number = (self.name or "").strip()
        if number and number != "/" and not (number.isdigit() and len(number) == 10):
            errors.append(
                _(
                    "Fiscal document number must be exactly 10 digits "
                    "(0000000001 to 9999999999). Current value: %s"
                )
                % number
            )

        pais = ""
        if self.partner_id.country_id and self.partner_id.country_id.dgi_code_id:
            pais = self.partner_id.country_id.dgi_code_id.code or ""
        elif self.partner_id.country_id:
            pais = "ZZ"
        if self.hka_destino_operacion == "1" and pais and pais != "PA":
            errors.append(
                _(
                    "Destination is Panama but the receiver country code is %s. "
                    "Set Destination to Foreign or use a Panama partner."
                )
                % pais
            )
        if self.hka_destino_operacion == "2" and pais == "PA":
            errors.append(
                _(
                    "Destination is Foreign but the receiver country code is PA. "
                    "Set Destination to Panama or use a foreign partner."
                )
            )

        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
            desc = (line.name or line.product_id.name or "").strip()
            if desc and len(desc) < 2:
                errors.append(
                    _("Line description must be at least 2 characters (HKA). Line: %s")
                    % desc
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

        combo_errors = self._hka_combination_errors()
        if combo_errors:
            raise UserError("\n".join(combo_errors))

        # Validate document type matches move type
        if self.move_type == "out_invoice":
            if self.hka_tipo_documento in ("04", "05", "06", "07"):
                raise UserError(
                    _(
                        "Invalid document type for customer invoice: '%s'. "
                        "Customer invoices must use document types 01, 03, 08, 09, or 10."
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
            cufe = self.reversed_entry_id.dgi_cufe or ""
            if not cufe:
                raise UserError(
                    _(
                        "Cannot send credit note: Original invoice CUFE not available. "
                        "The original invoice (%s) must be sent to DGI first before creating a credit note."
                    )
                    % self.reversed_entry_id.name
                )
            if self.hka_tipo_documento == "04" and len(cufe) != 66:
                raise UserError(
                    _(
                        "Cannot send credit note: referenced CUFE must be 66 characters "
                        "(HKA cufeFEReferenciada). Current length: %s"
                    )
                    % len(cufe)
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

        self.env.cr.execute(
            "SELECT id FROM account_move WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset(["dgi_sent", "dgi_status", "dgi_cufe"])
        if self.dgi_sent:
            raise UserError(_("This document has already been sent to DGI"))

        hka_api = self.env["l10n_pa_edi.hka_api"]
        document_data = self._prepare_dgi_document_data()
        result = hka_api.enviar(document_data, move_id=self.id)

        fields_to_write = {
            "dgi_status": result["status"],
            "dgi_sent_date": fields.Datetime.now(),
            "dgi_error_message": result["error_message"],
            "dgi_cufe": result["dgi_cufe"],
            "dgi_qr": result["dgi_qr"],
            "dgi_fecha_recepcion": result["dgi_fecha_recepcion"],
            "dgi_protocolo_autorizacion": result["dgi_protocolo_autorizacion"],
        }
        if result["success"]:
            fields_to_write["dgi_sent"] = True
            self._dgi_commit_api_fields(fields_to_write)
        else:
            self._dgi_write_api_fields(fields_to_write)

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

    def _dgi_moves_to_auto_send(self):
        """Posted customer invoices/refunds whose journal sends to DGI on confirm."""
        return self.filtered(
            lambda move: (
                move.state == "posted"
                and move.move_type in ("out_invoice", "out_refund")
                and move.journal_id.use_dgi_electronic_invoicing
                and move.journal_id.dgi_auto_send_on_post
                and not move.dgi_sent
            )
        )

    def _register_dgi_auto_send(self):
        """Call HKA only after the posting transaction commits.

        Enviar is irreversible. Sending inside ``_post`` meant a later rollback
        could drop the Odoo invoice while DGI already had a fiscal document.
        """
        move_ids = self.ids
        dbname = self.env.cr.dbname
        uid = self.env.uid
        context = dict(self.env.context)

        @self.env.cr.postcommit.add
        def _send_to_dgi_after_commit():
            db_registry = Registry(dbname)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, uid, context)
                for move in env["account.move"].browse(move_ids).exists():
                    try:
                        move._send_to_dgi_auto()
                        cr.commit()
                    except Exception:
                        cr.rollback()
                        _logger.exception(
                            "Failed to automatically send invoice %s to DGI after commit",
                            move.name,
                        )

    def _post(self, soft=True):
        """Queue DGI auto-send after the posting transaction commits."""
        res = super()._post(soft=soft)
        moves_to_send = self._dgi_moves_to_auto_send()
        if moves_to_send:
            moves_to_send._register_dgi_auto_send()
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

    def _need_cancel_request(self):
        """Block direct cancel of a procesado e-factura; allow it after DGI anulación."""
        if self.dgi_status == "anulado":
            return False
        if self.dgi_status == "procesado" and self.dgi_sent:
            return True
        return super()._need_cancel_request()

    def button_request_cancel(self):
        """Override to open DGI cancellation wizard when invoice is sent to DGI"""
        # If invoice is sent to DGI, use DGI cancellation wizard
        if self.dgi_sent and self.dgi_status == "procesado":
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
        """Block cancel of a live DGI invoice; allow Odoo cancel after DGI anulación."""
        for move in self:
            if move.dgi_sent and move.dgi_status == "procesado":
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

    def _hka_dgi_code_merge_key(self, line):
        """Group key for same-code merge. Unmapped products stay on their own line."""
        self.ensure_one()
        product = line.product_id
        dgi = product.dgi_code_id if product else False
        if not dgi:
            return ("line", line.id)
        isc_rate = None
        for tax in line.tax_ids:
            if tax.hka_tax_code == "04" and tax.hka_tax_isc_id:
                isc_rate = round(float(tax.hka_tax_isc_id.rate), 6)
                break
        uom_id = line.product_uom_id.id if line.product_uom_id else 0
        return ("code", dgi.id, self._hka_itbms_tasa_for_line(line), isc_rate, uom_id)

    def _hka_line_tax_amounts(self, line):
        """Signed ITBMS/ISC amounts for one product line."""
        self.ensure_one()
        itbms_tasa = None
        itbms = 0.0
        isc_rate = None
        isc = 0.0
        if not line.tax_ids:
            return itbms_tasa, itbms, isc_rate, isc
        base_line = self._prepare_product_base_line_for_taxes_computation(line)
        self.env["account.tax"]._add_tax_details_in_base_line(base_line, self.company_id)
        for tax_data in base_line.get("tax_details", {}).get("taxes_data", []):
            tax = tax_data.get("tax")
            if not tax or not tax.hka_tax_code:
                continue
            amount = tax_data.get("raw_tax_amount_currency", 0.0)
            if tax.hka_tax_code in ("00", "01", "02", "03"):
                itbms_tasa = tax.hka_tax_code
                itbms += amount
            elif tax.hka_tax_code == "04" and tax.hka_tax_isc_id:
                isc_rate = tax.hka_tax_isc_id.rate
                isc += amount
        return itbms_tasa, itbms, isc_rate, isc

    def _hka_prepare_line_item(self, line):
        """One HKA listaItems row from a single positive invoice line."""
        self.ensure_one()
        item = {
            "descripcion": self._hka_normalize_lista_item_descripcion(
                line.name or line.product_id.name or ""
            ),
            "cantidad": "{:.2f}".format(line.quantity),
            "precioUnitario": "{:.2f}".format(line.price_unit),
            "precioItem": "{:.2f}".format(line.price_subtotal),
            "valorTotal": "{:.2f}".format(line.price_total),
        }
        if line.discount > 0:
            discount_amount = line.price_unit * (line.discount / 100)
            item["precioUnitarioDescuento"] = "{:.2f}".format(discount_amount)

        if line.product_id and line.product_id.default_code:
            item["codigo"] = line.product_id.default_code[:20]

        item["unidadMedida"] = line.product_uom_id.dgi_code_id.code

        if getattr(line, "is_downpayment", False):
            item["unidadMedida"] = "und"

        item.update(
            self._hka_cpbs_fields(line.product_id, item.get("unidadMedida"))
        )

        if line.tax_ids:
            base_line = self._prepare_product_base_line_for_taxes_computation(line)
            self.env["account.tax"]._add_tax_details_in_base_line(
                base_line, self.company_id
            )
            for tax_data in base_line.get("tax_details", {}).get("taxes_data", []):
                tax = tax_data.get("tax")
                if tax and tax.hka_tax_code:
                    tax_amount = abs(tax_data.get("raw_tax_amount_currency", 0.0))
                    if tax.hka_tax_code in ("00", "01", "02", "03"):
                        item["tasaITBMS"] = tax.hka_tax_code
                        item["valorITBMS"] = "{:.2f}".format(tax_amount)
                    elif tax.hka_tax_code == "04":
                        item["tasaISC"] = str(tax.hka_tax_isc_id.rate)
                        item["valorISC"] = "{:.2f}".format(tax_amount)
        item.setdefault("tasaITBMS", "00")
        item.setdefault("valorITBMS", "0.00")
        return item

    def _hka_format_merged_unit_price(self, precio_item, qty):
        """Pick a unit price so cantidad * precioUnitario == precioItem (HKA)."""
        if qty <= 0:
            return None
        for decimals in (2, 3, 4, 5, 6):
            unit = round(precio_item / qty, decimals)
            if abs(self.currency_id.round(unit * qty) - precio_item) < 0.005:
                return ("%%.%df" % decimals) % unit
        return None

    def _hka_positive_qty_lines_for_merge(self, lines):
        """Lines that contribute quantity to a merged e-factura item."""
        self.ensure_one()
        rnd = self.currency_id.rounding or 0.01
        return lines.filtered(
            lambda line: line.quantity > 0
            and float_compare(line.price_subtotal, 0.0, precision_rounding=rnd) >= 0
        )

    def _hka_prepare_merged_item_from_lines(self, lines):
        """Net one HKA item from lines that share a DGI code. None if the net is invalid."""
        self.ensure_one()
        rnd = self.currency_id.rounding or 0.01
        pos_lines = self._hka_positive_qty_lines_for_merge(lines)
        qty = sum(pos_lines.mapped("quantity"))
        precio_item = self.currency_id.round(sum(lines.mapped("price_subtotal")))
        if qty <= 0 or float_compare(precio_item, 0.0, precision_rounding=rnd) < 0:
            return None

        ref = pos_lines[:1] or lines[:1]
        fallback = ref.name or ref.product_id.name or _("Invoice")
        unit_str = self._hka_format_merged_unit_price(precio_item, qty)
        if not unit_str:
            qty = 1.0
            unit_str = "{:.2f}".format(precio_item)
        item = {
            "descripcion": self._hka_join_descriptions_for_lines(lines, fallback),
            "cantidad": "{:.2f}".format(qty),
            "precioUnitario": unit_str,
            "precioItem": "{:.2f}".format(precio_item),
            "valorTotal": "{:.2f}".format(precio_item),
        }
        codes = {
            product.default_code
            for product in lines.mapped("product_id")
            if product.default_code
        }
        if len(codes) == 1:
            item["codigo"] = codes.pop()[:20]
        elif ref.product_id and ref.product_id.default_code:
            item["codigo"] = ref.product_id.default_code[:20]

        if any(getattr(line, "is_downpayment", False) for line in lines):
            item["unidadMedida"] = "und"
        else:
            uoms = {
                line.product_uom_id.dgi_code_id.code
                for line in pos_lines
                if line.product_uom_id.dgi_code_id
            }
            if len(uoms) == 1:
                item["unidadMedida"] = uoms.pop()
            elif ref.product_uom_id.dgi_code_id:
                item["unidadMedida"] = ref.product_uom_id.dgi_code_id.code
            else:
                item["unidadMedida"] = "und"

        item.update(self._hka_cpbs_fields(ref.product_id, item.get("unidadMedida")))

        itbms_tasa = None
        isc_rate = None
        isc = 0.0
        for line in lines:
            line_tasa, _line_itbms, line_isc_rate, line_isc = self._hka_line_tax_amounts(
                line
            )
            if line_tasa:
                itbms_tasa = line_tasa
            if line_isc_rate is not None:
                isc_rate = line_isc_rate
                isc += line_isc
        item["tasaITBMS"] = itbms_tasa or "00"
        # Tax the merged net. Summing per-line rounded ITBMS fails HKA when
        # many small lines accumulate (7 x 0.33 -> 0.14 vs 2.31 * 7% = 0.16).
        itbms = self._hka_itbms_amount_from_base(precio_item, item["tasaITBMS"])
        item["valorITBMS"] = "{:.2f}".format(itbms)
        if isc_rate is not None:
            item["tasaISC"] = str(isc_rate)
            item["valorISC"] = "{:.2f}".format(self.currency_id.round(isc))
        self._hka_sync_item_valor_total(item)
        return item

    def _hka_prepare_merged_items_by_dgi_code(self, product_lines):
        """One listaItems row per DGI code (+ tax). None if a group cannot be sent as-is."""
        self.ensure_one()
        groups = defaultdict(lambda: self.env["account.move.line"])
        for line in product_lines:
            groups[self._hka_dgi_code_merge_key(line)] |= line

        items = []
        for _key, lines in sorted(groups.items(), key=lambda kv: min(kv[1].ids)):
            if len(lines) == 1 and not self._hka_line_requires_consolidated_payload(
                lines
            ):
                items.append(self._hka_prepare_line_item(lines))
                continue
            item = self._hka_prepare_merged_item_from_lines(lines)
            if item is None:
                return None
            items.append(item)
        return items

    def _hka_line_requires_consolidated_payload(self, line):
        """Line cannot be sent as-is to HKA: negative quantity or negative untaxed subtotal."""
        move = line.move_id
        rnd = move.currency_id.rounding or 0.01
        if line.quantity < 0:
            return True
        return float_compare(line.price_subtotal, 0.0, precision_rounding=rnd) < 0

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
        }
        if self.hka_tipo_emision in HKA_CONTINGENCY_EMISSION:
            datos_transaccion["fechaInicioContingencia"] = self._format_dgi_datetime(
                self.hka_fecha_inicio_contingencia
            )
            datos_transaccion["motivoContingencia"] = (
                self.hka_motivo_contingencia or ""
            ).strip()
        if (
            self.move_type == "out_invoice"
            and self.hka_tipo_documento in HKA_TIPO_VENTA_DOCUMENTS
            and self.hka_tipo_venta
        ):
            datos_transaccion["tipoVenta"] = self.hka_tipo_venta
        interes = self._prepare_dgi_informacion_interes()
        if interes:
            datos_transaccion["informacionInteres"] = interes

        # Prepare invoice line items (exclude qty <= 0: HKA rejects invalid cantidad)
        product_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type == "product"
        )
        item_lines = product_lines.filtered(lambda l: l.quantity > 0)
        consolidate_lines = product_lines.filtered(
            lambda l: self._hka_line_requires_consolidated_payload(l)
        )

        if consolidate_lines and not item_lines:
            raise UserError(
                _(
                    "Cannot send to DGI: invoice has no product line with positive quantity. "
                    "At least one such line is required when other lines have negative quantity "
                    "or negative subtotal."
                )
            )

        # tax_totals: merged by HKA tasa / ISC rate; signed amounts match the move net of lines
        tax_totals_dict = self.tax_totals if isinstance(self.tax_totals, dict) else {}
        tax_parsed = self._hka_parse_tax_totals_for_hka(tax_totals_dict)
        total_itbms = tax_parsed["total_itbms"]
        total_isc = tax_parsed["total_isc"]

        lista_items = []
        merged_items = None
        if self.hka_merge_same_dgi_code:
            merged_items = self._hka_prepare_merged_items_by_dgi_code(product_lines)
        if merged_items:
            lista_items = merged_items
            total_itbms = self.currency_id.round(
                sum(float(item.get("valorITBMS") or 0.0) for item in lista_items)
            )
            total_isc = self.currency_id.round(
                sum(float(item.get("valorISC") or 0.0) for item in lista_items)
            )
        elif consolidate_lines:
            lista_items = self._hka_prepare_consolidated_invoice_items(
                item_lines, tax_parsed
            )
        else:
            lista_items = [
                self._hka_prepare_line_item(line) for line in item_lines
            ]
            self._hka_reconcile_lista_items_itbms(
                lista_items, product_lines, total_itbms
            )

        if not lista_items:
            raise UserError(
                _("Cannot send to DGI: invoice has no product lines for e-factura items.")
            )

        hka_total = self.currency_id.round(
            self.amount_untaxed + total_itbms + total_isc
        )

        # Build totalesSubTotales
        totales_sub_totales = {
            "totalPrecioNeto": "{:.2f}".format(self.amount_untaxed),
            "totalITBMS": "{:.2f}".format(total_itbms),
            "totalMontoGravado": "{:.2f}".format(total_itbms + total_isc),
            "totalFactura": "{:.2f}".format(hka_total),
            "totalValorRecibido": "{:.2f}".format(hka_total),
            "totalTodosItems": "{:.2f}".format(hka_total),
            "tiempoPago": "2" if self.hka_forma_pago == "01" else "1",
            "nroItems": str(len(lista_items)),
            "listaFormaPago": [
                {
                    "formaPagoFact": self.hka_forma_pago,
                    "valorCuotaPagada": "{:.2f}".format(hka_total),
                    **(
                        {"descFormaPago": self.hka_desc_forma_pago.strip()}
                        if self.hka_forma_pago == "99" and self.hka_desc_forma_pago
                        else {}
                    ),
                }
            ],
        }

        # Add ISC total if present
        if total_isc > 0:
            totales_sub_totales["totalISC"] = "{:.2f}".format(total_isc)

        if (
            self.hka_destino_operacion == "2"
            or self.partner_id.dgi_tipo_cliente_fe == "04"
        ):
            if not self.invoice_incoterm_id or not self.invoice_incoterm_id.dgi_code_id:
                raise UserError(
                    _("Incoterm DGI code is not set for incoterm %s")
                    % (self.invoice_incoterm_id.name if self.invoice_incoterm_id else "")
                )
            export_vals = {
                "condicionesEntrega": self.invoice_incoterm_id.dgi_code_id.code,
                "monedaOperExportacion": self.currency_id.dgi_code_id.code,
            }
            if self.currency_id.name != "USD":
                usd = self.env.ref("base.USD")
                rate = self.currency_id._convert(
                    1.0,
                    usd,
                    self.company_id,
                    self.invoice_date or fields.Date.context_today(self),
                )
                export_vals["tipoDeCambio"] = "{:.4f}".format(rate)
                export_vals["montoMonedaExtranjera"] = "{:.4f}".format(
                    rate * self.amount_total
                )
            datos_transaccion["datosFacturaExportacion"] = export_vals

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
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only accounting managers can open HKA API logs."))
        return {
            "type": "ir.actions.act_window",
            "name": "HKA API Logs",
            "res_model": "hka.api.log",
            "view_mode": "list,form",
            "domain": [("move_id", "=", self.id)],
            "context": {"default_move_id": self.id},
        }
