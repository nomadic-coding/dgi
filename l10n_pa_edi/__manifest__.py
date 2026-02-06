# -*- coding: utf-8 -*-
{
    "name": "Panama - Electronic Invoicing",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Panama Electronic Invoicing with HKA API",
    "description": """
Panama Electronic Invoicing - HKA Integration
==============================================
This module implements electronic invoicing for Panama using The Factory HKA API.

Features:
---------
* RUC validation with DGI (ConsultaRucDv endpoint)
* Electronic invoice sending (Enviar endpoint)
* Customer management with DGI fields
* Invoice preparation according to DGI requirements
* Integration with l10n_pa_location for addresses

API Documentation: https://felwiki.thefactoryhka.com.pa/
    """,
    "author": "STARK LABS",
    "website": "https://www.starklabspanama.com",
    "depends": [
        "account",
        "sale",
        "l10n_pa",
        "l10n_pa_location",
        "l10n_pa_dgi_code_mapping",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/account_tax_isc.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/account_journal_views.xml",
        "views/account_tax_views.xml",
        "views/account_move_views.xml",
        "views/dgi_anulacion_wizard_views.xml",
        "views/hka_api_log_views.xml",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
