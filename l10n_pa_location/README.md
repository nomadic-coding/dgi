# Panama Location Module (l10n_pa_location)

## Overview
This module provides comprehensive location management for Panama's administrative divisions structure for Odoo 18.0.

## Features

### Administrative Divisions
- **Provincia** (Province): 13 provinces including comarcas
- **Distrito** (District): Districts within each province  
- **Corregimiento** (Corregimiento): Corregimientos within each district
- **CODIGO_UBICACION**: Unique location code in format X-Y-Z

### Key Functionality
- ✅ Complete Panama location database pre-loaded (all official locations)
- ✅ Hierarchical location structure with proper relationships
- ✅ Integration with partner addresses (`res.partner`)
- ✅ Auto-sync `zip` field with `CODIGO_UBICACION` for Panama addresses
- ✅ Smart cascading fields with proper domain filtering
- ✅ Compatible with DGI fiscal requirements

### Partner Address Enhancement
When a partner's country is set to Panama (PA):
- Select Province → District → Corregimiento in cascade
- `zip` field automatically populated with `CODIGO_UBICACION`
- Location code (e.g., "8-8-1") stored for DGI documents

## Installation
1. Copy module to addons directory
2. Update apps list
3. Install "Panama - Locations" module
4. All location data loads automatically

## Usage
Navigate to **Contacts → Configuration → Panama Locations** to manage:
- Districts
- Corregimientos

On partner form, Panama address fields appear when Country = Panama.

## Technical Details
- **Odoo Version**: 18.0
- **Models**: 
  - `l10n.pa.distrito` (District)
  - `l10n.pa.corregimiento` (Corregimiento)
  - Extends `res.partner` and `res.country.state`
- **Data**: 13 provinces, 75+ districts, 600+ corregimientos

## Compatibility
- Standalone module (no OCA dependencies)
- Works with vanilla Odoo 18.0
- Compatible with DGI modules (`st_dgi_base`, `st_dgi_hka`)

