# -*- coding: utf-8 -*-

import json
import logging
import threading

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class HkaApiLog(models.Model):
    _name = "hka.api.log"
    _description = "HKA API Call Log"
    _order = "create_date desc"

    # Constants
    API_METHODS = [
        ("consulta_ruc_dv", "ConsultaRucDv - RUC Validation"),
        ("enviar", "Enviar - Send Invoice"),
        ("consultar", "Consultar - Query Invoice"),
        ("anular", "Anular - Cancel Invoice"),
        ("descarga", "Descarga - Download Invoice"),
    ]

    STATUS = [
        ("success", "Success"),
        ("error", "Error"),
        ("pending", "Pending"),
    ]

    # Relations
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        ondelete="cascade",
        index=True,
        help="Related invoice/move for this API call",
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    # Logs are committed on their own cursor so they survive a rollback of the
    # sending transaction. A move_id FK would wait on the account.edi
    # ``FOR UPDATE`` lock of the invoice, so detached logs link to the invoice
    # through this key instead (see ``account.move._hka_api_log_domain``).
    document_key = fields.Char(
        string="Document Key",
        index=True,
        readonly=True,
        help="codigoSucursalEmisor|puntoFacturacionFiscal|tipoDocumento|"
        "numeroDocumentoFiscal of the HKA document this call concerns.",
    )
    document_number = fields.Char(
        string="Document Number",
        readonly=True,
        help="HKA numeroDocumentoFiscal (10 digits).",
    )
    dgi_cufe = fields.Char(
        string="CUFE",
        readonly=True,
        help="CUFE returned by HKA for an accepted Enviar. Kept so the invoice "
        "can recover it after a lost transaction (HKA code 102).",
    )

    # API Call Information
    api_method = fields.Selection(
        selection=API_METHODS,
        string="API Method",
        required=True,
        index=True,
        help="DGI API endpoint called",
    )

    status = fields.Selection(
        selection=STATUS,
        string="Status",
        required=True,
        default="pending",
        index=True,
    )

    # Request/Response Data
    request_data = fields.Text(
        string="Request Data",
        help="JSON payload sent to DGI API",
    )

    response_data = fields.Text(
        string="Response Data",
        help="JSON response received from DGI API",
    )

    error_message = fields.Text(
        string="Error Message",
        help="Error details if the call failed",
    )

    # Metadata
    http_status_code = fields.Integer(
        string="HTTP Status Code",
        help="HTTP response status code",
    )

    duration_ms = fields.Float(
        string="Duration (ms)",
        help="API call duration in milliseconds",
    )

    @api.depends("api_method", "move_id.name", "document_number")
    def _compute_display_name(self):
        """Generate display name for the log entry."""
        methods = dict(self.API_METHODS)
        for log in self:
            method_name = methods.get(log.api_method, log.api_method)
            move_ref = log.move_id.name or log.document_number or _("N/A")
            log.display_name = f"{method_name} - {move_ref}"

    SENSITIVE_KEYS = frozenset({
        "clave",
        "password",
        "token",
        "access_token",
        "authtoken",
        "jwt",
        "authorization",
        "usuario",
        "archivo",
        "file_content",
        "auth_token",
        "hka_clave",
        "hka_usuario",
        "hka_auth_token",
    })

    @api.model
    def _redact_payload(self, data):
        """Strip credentials from stored request/response JSON."""
        if isinstance(data, dict):
            redacted = {}
            for key, value in data.items():
                if str(key).lower() in self.SENSITIVE_KEYS:
                    redacted[key] = "***"
                else:
                    redacted[key] = self._redact_payload(value)
            return redacted
        if isinstance(data, list):
            return [self._redact_payload(item) for item in data]
        return data

    # ------------------------------------------------------------------
    # Document key helpers
    # ------------------------------------------------------------------
    @api.model
    def _document_key_from_parts(self, sucursal, punto, tipo_documento, numero):
        parts = [str(part or "").strip() for part in (sucursal, punto, tipo_documento, numero)]
        if not parts[3] or parts[3] == "/":
            return False
        return "|".join(parts)

    @api.model
    def _document_key_from_payload(self, document_data):
        """Key of an HKA Enviar payload (``{"documento": {...}}``)."""
        documento = (document_data or {}).get("documento") or {}
        datos = documento.get("datosTransaccion") or {}
        return self._document_key_from_parts(
            documento.get("codigoSucursalEmisor"),
            datos.get("puntoFacturacionFiscal"),
            datos.get("tipoDocumento"),
            datos.get("numeroDocumentoFiscal"),
        )

    @api.model
    def _document_key_from_move(self, move):
        """Key of the HKA document an invoice is (or will be) sent as."""
        if not move or not move.name or move.name == "/":
            return False
        return self._document_key_from_parts(
            move.journal_id.dgi_codigo_sucursal_emisor,
            move.journal_id.dgi_punto_facturacion_fiscal,
            move.hka_tipo_documento,
            move.name,
        )

    @api.model
    def _document_number_from_key(self, document_key):
        if not document_key:
            return False
        return document_key.rsplit("|", 1)[-1] or False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    @api.model
    def _prepare_log_values(
        self,
        api_method,
        request_data=None,
        response_data=None,
        status="pending",
        error_message=None,
        http_status_code=None,
        duration_ms=None,
        move_id=None,
        document_key=None,
        dgi_cufe=None,
    ):
        values = {
            "api_method": api_method,
            "status": status,
            "http_status_code": http_status_code,
            "duration_ms": duration_ms,
            "move_id": move_id,
            "company_id": self.env.company.id,
        }
        if move_id:
            move = self.env["account.move"].browse(move_id)
            if move.exists():
                if move.company_id:
                    values["company_id"] = move.company_id.id
                if not document_key:
                    document_key = self._document_key_from_move(move)
        if document_key:
            values["document_key"] = document_key
            values["document_number"] = self._document_number_from_key(document_key)
        if dgi_cufe:
            values["dgi_cufe"] = dgi_cufe

        if request_data:
            values["request_data"] = json.dumps(
                self._redact_payload(request_data), indent=2, ensure_ascii=False
            )

        if response_data:
            values["response_data"] = json.dumps(
                self._redact_payload(response_data), indent=2, ensure_ascii=False
            )

        if error_message:
            values["error_message"] = str(
                self._redact_payload({"error": str(error_message)}).get("error")
            )
        return values

    @api.model
    def _create_detached(self, values):
        """Create and commit a log row on its own cursor.

        The row survives a rollback of the calling transaction, which is what
        makes an accepted Enviar recoverable. ``move_id`` is never set here:
        the FK would wait on the ``FOR UPDATE`` lock account.edi holds on the
        invoice. Returns the new id, or None when the insert failed.
        """
        values = dict(values, move_id=False)
        if getattr(threading.current_thread(), "testing", False):
            # Tests run inside one uncommitted transaction that a second
            # connection cannot see (same precedent as mail.mail.send):
            # keep the row in the test transaction, still without the FK.
            return self.sudo().create(values).id
        try:
            with self.env.registry.cursor() as new_cr:
                new_env = api.Environment(new_cr, self.env.uid, {})
                log = new_env["hka.api.log"].sudo().create(values)
                new_cr.commit()
                return log.id
        except Exception:
            _logger.error(
                "Failed to create detached HKA API log entry (%s, %s)",
                values.get("api_method"),
                values.get("document_key"),
                exc_info=True,
            )
            return None

    def log_api_call(
        self,
        api_method,
        request_data=None,
        response_data=None,
        status="pending",
        error_message=None,
        http_status_code=None,
        duration_ms=None,
        move_id=None,
        auto_commit=True,
        document_key=None,
        dgi_cufe=None,
    ):
        """
        Create a log entry for a HKA API call.

        By default the log is written and committed on an independent cursor
        so it survives a rollback of the main transaction (lost CUFE, UserError
        raised after the call, ...). Such rows carry no ``move_id``; they are
        linked to the invoice through ``document_key``.

        Args:
            api_method (str): API method name from API_METHODS
            request_data (dict): Request payload
            response_data (dict): Response data
            status (str): Call status (success/error/pending)
            error_message (str): Error message if any
            http_status_code (int): HTTP status code
            duration_ms (float): Call duration in milliseconds
            move_id (int): Related move ID (used for company and document key)
            auto_commit (bool): True (default) writes on an independent cursor.
                False creates the row in the current transaction with move_id.
            document_key (str): HKA document key; derived from move_id if omitted
            dgi_cufe (str): CUFE accepted by HKA (Enviar receipts)

        Returns:
            int | hka.api.log | None: the detached row id (or None when the
            insert failed) with auto_commit=True, else the created record.
        """
        values = self._prepare_log_values(
            api_method,
            request_data=request_data,
            response_data=response_data,
            status=status,
            error_message=error_message,
            http_status_code=http_status_code,
            duration_ms=duration_ms,
            move_id=move_id,
            document_key=document_key,
            dgi_cufe=dgi_cufe,
        )
        if auto_commit:
            return self._create_detached(values)
        return self.sudo().create(values)

    # ------------------------------------------------------------------
    # Enviar receipts
    # ------------------------------------------------------------------
    @api.model
    def _find_enviar_receipt(self, company, document_key):
        """Latest accepted Enviar log for this HKA document in this company."""
        if not document_key or not company:
            return self.browse()
        return self.sudo().search(
            [
                ("api_method", "=", "enviar"),
                ("status", "=", "success"),
                ("company_id", "=", company.id),
                ("document_key", "=", document_key),
                ("dgi_cufe", "!=", False),
            ],
            order="create_date desc, id desc",
            limit=1,
        )

    def _enviar_receipt_payloads(self):
        """(request, response) dicts stored on an Enviar receipt."""
        self.ensure_one()
        try:
            request = json.loads(self.request_data or "{}")
            response = json.loads(self.response_data or "{}")
        except ValueError:
            return {}, {}
        return (
            request if isinstance(request, dict) else {},
            response if isinstance(response, dict) else {},
        )

    @api.model
    def _backfill_document_keys(self):
        """Fill document_key / document_number / dgi_cufe on logs created before
        detached logging existed. Idempotent; run on upgrade."""
        logs = self.sudo().search([
            ("move_id", "!=", False),
            ("document_key", "=", False),
        ])
        for log in logs:
            key = self._document_key_from_move(log.move_id)
            if not key:
                continue
            vals = {
                "document_key": key,
                "document_number": self._document_number_from_key(key),
            }
            if log.api_method == "enviar" and log.status == "success" and not log.dgi_cufe:
                _request, response = log._enviar_receipt_payloads()
                if response.get("cufe"):
                    vals["dgi_cufe"] = response["cufe"]
            log.write(vals)
