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
- **Merge Same DGI Code Lines**: Default for new invoices; group e-factura lines that share the same DGI product/service code into one line sent as quantity 1 with the net total as unit price. Override on each invoice's Electronic Invoice (DGI) tab.
- **Sale Type (`tipoVenta`)**: Required on customer invoices (giro, asset, real estate, or service). Not sent on credit notes.

Posted DGI invoices use Odoo's `account.edi` format **Panama DGI (HKA)**. Sending is queued on post and processed by **Process now** or the electronic invoicing cron.

Upgrading from 18.0.1.0.0 attaches that format to existing DGI journals and backfills EDI documents. Invoices that already have a CUFE become `sent` (or `cancelled` if anulado). Posted invoices that were never sent are queued with a blocking error so the cron does not call Enviar; use **Retry** to send them.

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
4. Click **Process now** on the electronic invoicing banner, or wait for the EDI cron
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
- `l10n.pa.edi.payload`: HKA Enviar payload builder (abstract model)
- `res.partner`: Extended with DGI fields and RUC validation
- `account.journal`: Extended with branch code
- `account.move`: Fiscal identity (CUFE/QR/status) and combination fields
- `account.edi.document`: Send/cancel queue for format `pa_dgi_hka`

### Key Methods

- `hka_api.validate_ruc(ruc, tipo_ruc)`: Validate RUC with DGI
- `hka_api.enviar(document_data)`: Send document to DGI
- `l10n.pa.edi.payload.prepare(move)`: Build the Enviar JSON
- `res.partner.action_validate_ruc()`: Validate partner's RUC
- `account.edi.format` `pa_dgi_hka`: post/cancel HKA documents via the standard EDI cron
- `account.move.action_send_to_dgi()`: Process the queued HKA EDI document now
- `account.move._prepare_dgi_document_data()`: Wrapper around `payload.prepare`

## Support

For issues and questions, refer to the HKA API documentation or contact The Factory HKA support.

## License

LGPL-3

