# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HkaApiLog(models.Model):
    _name = "hka.api.log"
    _description = "HKA API Call Log"
    _order = "create_date desc"
    _rec_name = "display_name"

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

    # Computed
    display_name = fields.Char(
        string="Name",
        compute="_compute_display_name",
    )

    def _compute_display_name(self):
        """Generate display name for the log entry."""
        for log in self:
            method_name = dict(self.API_METHODS).get(log.api_method, log.api_method)
            move_ref = log.move_id.name if log.move_id else "N/A"
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
    ):
        """
        Create a log entry for a HKA API call.

        This method automatically uses a new database cursor to ensure
        the log is committed even if the main transaction is rolled back.

        Args:
            api_method (str): API method name from API_METHODS
            request_data (dict): Request payload
            response_data (dict): Response data
            status (str): Call status (success/error/pending)
            error_message (str): Error message if any
            http_status_code (int): HTTP status code
            duration_ms (float): Call duration in milliseconds
            move_id (int): Related move ID
            auto_commit (bool): If True, uses a new cursor and commits independently.
                               Set to False only if you want to handle transaction manually.

        Returns:
            hka.api.log: Created log record (or None if auto_commit=True)
        """
        import json

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
            if move.exists() and move.company_id:
                values["company_id"] = move.company_id.id

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

        # Use a new cursor to ensure the log is committed
        # even if the main transaction is rolled back
        if auto_commit:
            # Never attach move_id on a side cursor: the FK waits on the Enviar
            # invoice lock and Process now then reports "another process already".
            values.pop("move_id", None)
            try:
                with self.env.registry.cursor() as new_cr:
                    new_env = api.Environment(new_cr, self.env.uid, self.env.context)
                    new_env["hka.api.log"].sudo().create(values)
                    new_cr.commit()
                    return None
            except Exception as exc:
                _logger.error("Failed to create API log entry: %s", exc)
                return None
        return self.sudo().create(values)
