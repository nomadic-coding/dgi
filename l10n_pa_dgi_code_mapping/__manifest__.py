# -*- coding: utf-8 -*-
{
    "name": "Panama - DGI Code Mapping",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "DGI Code Mappings for Panama",
    "description": """
Panama DGI Code Mapping
=======================
This module provides DGI code mappings for Panama electronic invoicing.

Features:
---------
* DGI code mapping model for various types (UoM, Country, Incoterm, Currency, Product/Service)
* Integration with standard Odoo models (product.template, res.country, res.currency, uom.uom, account.incoterms)
* Configuration menu accessible in debug mode
* Pre-loaded DGI codes data

This module can be used independently or with l10n_pa_edi for electronic invoicing.
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "depends": [
        "account",
        "product",
        "uom",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/dgi.code.mapping.csv",
        "views/dgi_code_mapping_views.xml",
        "views/product_template_views.xml",
        "views/res_country_views.xml",
        "views/account_incoterms_views.xml",
        "views/res_currency_views.xml",
        "views/uom_uom_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}

