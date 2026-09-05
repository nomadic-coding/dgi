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


def post_init_hook(env):
    _migrate_hka_icp_to_company(env)
