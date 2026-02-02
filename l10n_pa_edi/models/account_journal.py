# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    # Constants
    DGI_BRANCH_CODE_LENGTH = 4
    DGI_FISCAL_POINT_LENGTH = 3

    # Fields
    use_dgi_electronic_invoicing = fields.Boolean(
        string="Use DGI Electronic Invoicing",
        default=False,
        help="Enable electronic invoicing for Panama DGI",
    )

    dgi_auto_send_on_post = fields.Boolean(
        string="Auto-Send to DGI on Confirm",
        default=False,
        help="Automatically send invoices to DGI when they are confirmed/posted. "
        "If disabled, invoices must be sent manually using the 'Send to DGI' button.",
    )

    dgi_codigo_sucursal_emisor = fields.Char(
        string="Branch Code",
        size=4,
        help="Branch/Office code for DGI Panama (4 digits, e.g. '0000')",
    )

    dgi_punto_facturacion_fiscal = fields.Char(
        string="Fiscal Point",
        size=3,
        help="Billing point for DGI Panama (3 digits, e.g. '001')",
    )

    dgi_sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        string="DGI Invoice Sequence",
        copy=False,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
        help="Dedicated sequence for DGI electronic invoices. "
        "This will be used instead of the standard journal sequence "
        "for outgoing invoices when DGI electronic invoicing is enabled.",
    )

    # Constraints
    @api.constrains(
        "use_dgi_electronic_invoicing",
        "dgi_codigo_sucursal_emisor",
        "dgi_punto_facturacion_fiscal",
        "dgi_sequence_id",
    )
    def _check_dgi_fields_format(self):
        """Validate DGI field formats when electronic invoicing is enabled."""
        for journal in self:
            if not journal.use_dgi_electronic_invoicing:
                continue

            self._validate_branch_code(journal)
            self._validate_fiscal_point(journal)
            self._validate_dgi_sequence(journal)

    @api.constrains("dgi_codigo_sucursal_emisor")
    def _check_codigo_sucursal_unique(self):
        """Ensure branch code is unique per company."""
        for journal in self:
            if not journal.dgi_codigo_sucursal_emisor:
                continue

            existing = self._find_duplicate_branch_code(journal)
            if existing:
                raise ValidationError(
                    _(
                        "Branch code '%(code)s' is already used by journal '%(journal)s'."
                    )
                    % {
                        "code": journal.dgi_codigo_sucursal_emisor,
                        "journal": existing.name,
                    }
                )

    @api.constrains("dgi_punto_facturacion_fiscal")
    def _check_punto_facturacion_fiscal_unique(self):
        """Ensure fiscal point is unique per company."""
        for journal in self:
            if not journal.dgi_punto_facturacion_fiscal:
                continue

            existing = self._find_duplicate_fiscal_point(journal)
            if existing:
                raise ValidationError(
                    _(
                        "Fiscal point '%(code)s' is already used by journal '%(journal)s'."
                    )
                    % {
                        "code": journal.dgi_punto_facturacion_fiscal,
                        "journal": existing.name,
                    }
                )

    # Private Helper Methods
    def _validate_branch_code(self, journal):
        """Validate branch code format (4 digits)."""
        code = journal.dgi_codigo_sucursal_emisor
        if not self._is_valid_numeric_code(code, self.DGI_BRANCH_CODE_LENGTH):
            raise ValidationError(
                _(
                    "Branch code must be exactly %(length)d digits (e.g. '0000'). "
                    "Current value: '%(value)s'"
                )
                % {"length": self.DGI_BRANCH_CODE_LENGTH, "value": code or ""}
            )

    def _validate_fiscal_point(self, journal):
        """Validate fiscal point format (3 digits)."""
        code = journal.dgi_punto_facturacion_fiscal
        if not self._is_valid_numeric_code(code, self.DGI_FISCAL_POINT_LENGTH):
            raise ValidationError(
                _(
                    "Fiscal point must be exactly %(length)d digits (e.g. '001'). "
                    "Current value: '%(value)s'"
                )
                % {"length": self.DGI_FISCAL_POINT_LENGTH, "value": code or ""}
            )

    def _validate_dgi_sequence(self, journal):
        """Validate that DGI sequence is configured."""
        if not journal.dgi_sequence_id:
            raise ValidationError(
                _(
                    "DGI Invoice Sequence is required when DGI electronic invoicing is enabled. "
                    "Please configure a sequence for journal '%(journal)s'."
                )
                % {"journal": journal.name}
            )

    def _is_valid_numeric_code(self, code, expected_length):
        """Check if code is a numeric string with the expected length."""
        return code and len(code) == expected_length and code.isdigit()

    def _find_duplicate_branch_code(self, journal):
        """Find another journal with the same branch code in the same company."""
        return self.search(
            [
                ("id", "!=", journal.id),
                ("company_id", "=", journal.company_id.id),
                ("dgi_codigo_sucursal_emisor", "=", journal.dgi_codigo_sucursal_emisor),
            ],
            limit=1,
        )

    def _find_duplicate_fiscal_point(self, journal):
        """Find another journal with the same fiscal point in the same company."""
        return self.search(
            [
                ("id", "!=", journal.id),
                ("company_id", "=", journal.company_id.id),
                (
                    "dgi_punto_facturacion_fiscal",
                    "=",
                    journal.dgi_punto_facturacion_fiscal,
                ),
            ],
            limit=1,
        )
