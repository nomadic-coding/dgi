# Panama Electronic Invoicing (l10n_pa_edi)

Simple, all-in-one module for Panama electronic invoicing with The Factory HKA API.

## Features

- **RUC Validation**: Validate customer RUC with DGI Panama using the ConsultaRucDv endpoint
- **Electronic Invoice Sending**: Send invoices to DGI using the Enviar endpoint
- **Customer Management**: Extend partners with DGI-specific fields
- **Branch Configuration**: Configure branch codes (Código Sucursal Emisor) per journal
- **Integration with l10n_pa_location**: Uses Panama's official location codes

## Installation

1. Install dependencies:
   - `l10n_pa` (Panama localization)
   - `l10n_pa_location` (Panama locations)
   - `l10n_pa_dgi_code_mapping` (DGI catalogs)

2. Install this module: `l10n_pa_edi`

HKA credentials are stored per company under **Settings > Panama Electronic Invoicing**.

## Configuration

Go to **Settings > General Settings > Panama Electronic Invoicing** and configure:

- **HKA API URL**: API endpoint (default: https://demointegracion.thefactoryhka.com.pa)
- **HKA Usuario**: Your HKA API username/token
- **HKA Clave**: Your HKA API password
- **API Timeout**: Request timeout in seconds (default: 30)
- **Verify SSL**: Enable/disable SSL verification
- **Merge Same DGI Code Lines**: Default for new invoices; group e-factura lines that share the same DGI product/service code. Override on each invoice's Electronic Invoice (DGI) tab.
- **Sale Type (`tipoVenta`)**: Required on customer invoices (giro, asset, real estate, or service). Not sent on credit notes.

## Usage

### 1. Configure Journal

Go to **Accounting > Configuration > Journals** and set:
- **Código Sucursal Emisor**: Branch code (0000 = main, 0001+ = branches)

### 2. Validate Customer RUC

1. Open a partner (customer)
2. Go to **DGI Panama** tab
3. Enter **Tipo RUC** and **RUC Number**
4. Click **Validate RUC**
5. System will validate with DGI and populate:
   - DV (Dígito Verificador)
   - Razón Social
   - Taxpayer Status

### 3. Send Invoice to DGI

1. Create and post an invoice
2. Go to **Electronic Invoice (DGI)** tab
3. Review/configure electronic invoice settings
4. Click **Send to DGI** button
5. System will send the invoice and display:
   - CUFE (Unique Electronic Invoice Code)
   - QR Code
   - Authorization Protocol
   - DGI Reception Date

## API Documentation

- HKA API Docs: https://felwiki.thefactoryhka.com.pa/
- ConsultaRucDv: https://felwiki.thefactoryhka.com.pa/consultarucdv_english
- Enviar: https://felwiki.thefactoryhka.com.pa/enviar_english

## Technical Details

### Models

- `l10n_pa_edi.hka_api`: HKA API client (abstract model)
- `res.partner`: Extended with DGI fields and RUC validation
- `account.journal`: Extended with branch code
- `account.move`: Extended with electronic invoice fields and sending logic

### Key Methods

- `hka_api.validate_ruc(ruc, tipo_ruc)`: Validate RUC with DGI
- `hka_api.enviar(document_data)`: Send document to DGI
- `res.partner.action_validate_ruc()`: Validate partner's RUC
- `account.move.action_send_to_dgi()`: Send invoice to DGI
- `account.move._prepare_dgi_document_data()`: Prepare document for API

## Support

For issues and questions, refer to the HKA API documentation or contact The Factory HKA support.

## License

LGPL-3

