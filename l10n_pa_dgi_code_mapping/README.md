# Panama - DGI Code Mapping

This module provides DGI (Dirección General de Ingresos) code mappings for Panama.

## Features

* **DGI Code Mapping Model**: Central model to store all DGI codes
* **Mapping Types**:
  - Unit of Measure
  - Country
  - Incoterm
  - Currency
  - Product/Service

* **Model Extensions**: Adds DGI code fields to:
  - `product.template`
  - `res.country`
  - `res.currency`
  - `uom.uom`
  - `account.incoterms`

* **Pre-loaded Data**: Includes DGI codes from official catalogues
* **Configuration Menu**: Accessible in debug mode under Accounting → Configuration

## Usage

This module can be used independently or as a dependency for electronic invoicing modules.

All DGI code fields are only visible in debug mode to prevent accidental modifications by regular users.

## Technical

* Module Name: `l10n_pa_dgi_code_mapping`
* Depends: `account`
* Odoo Version: 18.0

