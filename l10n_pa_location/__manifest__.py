# -*- coding: utf-8 -*-
{
    "name": "Panama - Locations (Provincia/Distrito/Corregimiento)",
    "version": "18.0.1.0.0",
    "category": "Localization",
    "summary": "Panama administrative divisions: Province, District, Corregimiento with CODIGO_UBICACION support",
    "description": """
        Panama Location System
        =======================
        
        This module provides a comprehensive location management system for Panama's
        administrative divisions structure:
        
        - **Provincia** (Province): 13 provinces + comarcas
        - **Distrito** (District): Districts within each province
        - **Corregimiento** (Corregimiento): Corregimientos within each district
        - **CODIGO_UBICACION**: Unique location code in format X-Y-Z
        
        Features:
        ---------
        * Hierarchical location structure (Province > District > Corregimiento)
        * Integration with partner addresses (res.partner)
        * Complete Panama location database pre-loaded
        * Location code (CODIGO_UBICACION) for official documents
        * Smart fields on partner form for cascading location selection
        * Compatible with DGI fiscal requirements
        
        Usage:
        ------
        Once installed, partner addresses will have additional fields for:
        - Provincia
        - Distrito  
        - Corregimiento
        - CODIGO_UBICACION (auto-computed)
        
        The module comes pre-loaded with all official Panama locations.
        
        Technical:
        ----------
        This module is inspired by OCA's base_location but adapted specifically
        for Panama's administrative structure and DGI requirements.
    """,
    "author": "STARK LABS",
    "website": "https://www.starklabspanama.com",
    "depends": [
        "base",
        "contacts",
    ],
    "data": [
        # Security
        "security/ir.model.access.csv",
        # Data - must be loaded in hierarchical order
        "data/res.country.state.csv",
        "data/l10n.pa.distrito.csv",
        "data/l10n.pa.corregimiento.csv",
        # Views
        "views/l10n_pa_location_views.xml",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}

