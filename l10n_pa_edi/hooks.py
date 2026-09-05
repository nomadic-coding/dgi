# -*- coding: utf-8 -*-


def _migrate_hka_icp_to_company(env):
    """Copy legacy database-wide HKA settings onto companies that have none."""
    ICP = env["ir.config_parameter"].sudo()
    raw = {
        "hka_api_url": ICP.get_param("l10n_pa_edi.hka_api_url"),
        "hka_usuario": ICP.get_param("l10n_pa_edi.hka_usuario"),
        "hka_clave": ICP.get_param("l10n_pa_edi.hka_clave"),
        "hka_timeout": ICP.get_param("l10n_pa_edi.hka_timeout"),
        "hka_verify_ssl": ICP.get_param("l10n_pa_edi.hka_verify_ssl"),
        "hka_auth_token": ICP.get_param("l10n_pa_edi.hka_auth_token"),
        "hka_auth_token_expiry": ICP.get_param("l10n_pa_edi.hka_auth_token_expiry"),
    }
    if not any(raw.values()):
        return

    vals = {}
    if raw["hka_api_url"]:
        vals["hka_api_url"] = raw["hka_api_url"]
    if raw["hka_usuario"]:
        vals["hka_usuario"] = raw["hka_usuario"]
    if raw["hka_clave"]:
        vals["hka_clave"] = raw["hka_clave"]
    if raw["hka_timeout"]:
        try:
            vals["hka_timeout"] = int(raw["hka_timeout"])
        except (TypeError, ValueError):
            vals["hka_timeout"] = 30
    if raw["hka_verify_ssl"] not in (None, False, ""):
        vals["hka_verify_ssl"] = raw["hka_verify_ssl"] == "True"
    if raw["hka_auth_token"]:
        vals["hka_auth_token"] = raw["hka_auth_token"]
    if raw["hka_auth_token_expiry"]:
        vals["hka_auth_token_expiry"] = raw["hka_auth_token_expiry"]

    if not vals:
        return

    for company in env["res.company"].sudo().search([]):
        if company.hka_usuario or company.hka_clave:
            continue
        company.write(vals)

    for key in (
        "l10n_pa_edi.hka_api_url",
        "l10n_pa_edi.hka_usuario",
        "l10n_pa_edi.hka_clave",
        "l10n_pa_edi.hka_timeout",
        "l10n_pa_edi.hka_verify_ssl",
        "l10n_pa_edi.hka_auth_token",
        "l10n_pa_edi.hka_auth_token_expiry",
    ):
        ICP.set_param(key, False)


def _auto_map_dgi_catalogs(env):
    """Link standard Odoo records to DGI catalog rows when still empty."""
    Mapping = env["dgi.code.mapping"].sudo()

    def _map_record(record, xmlid):
        if not record or record.dgi_code_id:
            return
        mapping = env.ref(xmlid, raise_if_not_found=False)
        if mapping:
            record.sudo().dgi_code_id = mapping

    _map_record(
        env.ref("base.pa", raise_if_not_found=False),
        "l10n_pa_dgi_code_mapping.dgi_mapping_917",
    )
    _map_record(
        env.ref("base.USD", raise_if_not_found=False),
        "l10n_pa_dgi_code_mapping.dgi_mapping_728",
    )
    _map_record(
        env.ref("base.PAB", raise_if_not_found=False),
        "l10n_pa_dgi_code_mapping.dgi_mapping_690",
    )
    _map_record(
        env.ref("uom.product_uom_unit", raise_if_not_found=False),
        "l10n_pa_dgi_code_mapping.dgi_mapping_504",
    )

    for currency in env["res.currency"].search(
        [("dgi_code_id", "=", False), ("name", "in", ("PAB", "USD"))]
    ):
        mapping = Mapping.search(
            [("mapping_type", "=", "currency"), ("code", "=", currency.name)],
            limit=1,
        )
        if mapping:
            currency.sudo().dgi_code_id = mapping


def _auto_map_l10n_pa_taxes(env):
    """Map the official Panama 7% sale ITBMS to HKA code 01 when empty."""
    Tax = env["account.tax"].sudo()
    for company in env["res.company"].search([]):
        tax = env.ref(f"account.{company.id}_ITAX_19", raise_if_not_found=False)
        if tax and not tax.hka_tax_code:
            tax.hka_tax_code = "01"
            continue
        unmapped = Tax.search(
            [
                ("company_id", "=", company.id),
                ("type_tax_use", "=", "sale"),
                ("amount", "=", 7.0),
                ("hka_tax_code", "=", False),
            ]
        )
        unmapped.write({"hka_tax_code": "01"})


HKA_UPGRADE_QUEUE_ERROR = (
    "Queued during the Panama DGI electronic invoicing upgrade. "
    "Click Retry to send this invoice to DGI."
)


def _drop_legacy_dgi_auto_send_column(cr):
    """Remove the retired journal flag after the field is gone from the model."""
    cr.execute(
        "ALTER TABLE account_journal DROP COLUMN IF EXISTS dgi_auto_send_on_post"
    )


def _enable_hka_edi_on_dgi_journals(env):
    """Attach the HKA EDI format to journals that already use DGI."""
    edi_format = env.ref("l10n_pa_edi.edi_format_pa_dgi_hka", raise_if_not_found=False)
    if not edi_format:
        return
    journals = env["account.journal"].search([
        ("use_dgi_electronic_invoicing", "=", True),
    ])
    if journals:
        journals.edi_format_ids |= edi_format


def _hka_edi_moves_missing_documents(env, edi_format, moves):
    if not moves:
        return env["account.move"]
    existing_move_ids = set(
        env["account.edi.document"].search([
            ("edi_format_id", "=", edi_format.id),
            ("move_id", "in", moves.ids),
        ]).mapped("move_id").ids
    )
    return moves.filtered(lambda move: move.id not in existing_move_ids)


def _backfill_hka_edi_documents(env):
    """Create EDI documents for invoices that existed before account.edi.

    Sent / anulado invoices get ``sent`` / ``cancelled``. Posted invoices that
    were never sent are queued as ``to_send`` with a blocking error so the EDI
    cron does not call Enviar during the upgrade. Users click Retry to send.
    """
    edi_format = env.ref("l10n_pa_edi.edi_format_pa_dgi_hka", raise_if_not_found=False)
    if not edi_format:
        return

    sent_moves = _hka_edi_moves_missing_documents(
        env,
        edi_format,
        env["account.move"].search([
            ("dgi_cufe", "!=", False),
            ("move_type", "in", ("out_invoice", "out_refund")),
        ]),
    )
    to_create = [
        {
            "move_id": move.id,
            "edi_format_id": edi_format.id,
            "state": "cancelled" if move.dgi_status == "anulado" else "sent",
        }
        for move in sent_moves
    ]

    unsent_moves = _hka_edi_moves_missing_documents(
        env,
        edi_format,
        env["account.move"].search([
            ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("journal_id.use_dgi_electronic_invoicing", "=", True),
            ("dgi_cufe", "=", False),
        ]),
    )
    to_create.extend(
        {
            "move_id": move.id,
            "edi_format_id": edi_format.id,
            "state": "to_send",
            "error": HKA_UPGRADE_QUEUE_ERROR,
            "blocking_level": "error",
        }
        for move in unsent_moves
    )
    if to_create:
        env["account.edi.document"].create(to_create)


def post_init_hook(env):
    _migrate_hka_icp_to_company(env)
    _auto_map_dgi_catalogs(env)
    _auto_map_l10n_pa_taxes(env)
    _enable_hka_edi_on_dgi_journals(env)
    _backfill_hka_edi_documents(env)
