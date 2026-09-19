# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    # DGI Panama Fields
    dgi_tipo_ruc = fields.Selection(
        [
            ("01", "1 - Natural Person"),
            ("02", "2 - Juridical Person"),
            ("03", "3 - Government Entity"),
            ("04", "4 - Foreign Entity"),
        ],
        string="Tipo RUC",
        help="Type of RUC for DGI Panama",
    )
    dgi_tipo_cliente_fe = fields.Selection(
        [
            ("01", "01 - Contribuyente (Taxpayer)"),
            ("02", "02 - Consumidor Final (Final Consumer)"),
            ("03", "03 - Gobierno (Government)"),
            ("04", "04 - Extranjero (Foreign)"),
        ],
        string="Tipo Cliente FE",
        compute="_compute_tipo_cliente_fe",
        store=True,
        help="Identifies the type of electronic invoice receiver",
    )
    dgi_tipo_contribuyente = fields.Selection(
        [
            ("1", "1 - Natural (Individual)"),
            ("2", "2 - Jurídico (Legal Entity)"),
        ],
        string="Tipo Contribuyente",
        compute="_compute_tipo_contribuyente",
        store=True,
        help="Type of taxpayer (not sent if foreign)",
    )
    dgi_ruc = fields.Char(
        string="RUC Number",
        help="RUC number for validation. Will be copied to VAT field after successful validation.",
    )
    dgi_dv = fields.Char(
        string="DV (Dígito Verificador)",
        help="Verification digit for RUC",
    )
    dgi_razon_social = fields.Char(
        string="Razón Social",
        help="Official business name from DGI",
    )
    dgi_taxpayer_status = fields.Char(
        string="Taxpayer Status",
        help="Status from DGI (e.g., Afiliado FE)",
    )
    dgi_ruc_validated = fields.Boolean(
        string="RUC Validated",
        default=False,
        readonly=True,
        copy=False,
        help="Set only after a successful DGI RUC validation. Cannot be checked by hand.",
    )
    dgi_ruc_validation_date = fields.Datetime(
        string="Validation Date",
        readonly=True,
        copy=False,
        help="Date when RUC was validated with DGI",
    )
    dgi_tipo_identificacion_extranjero = fields.Selection(
        [
            ("01", "01 - Pasaporte (Passport)"),
            ("02", "02 - Número Tributario (Tax Number)"),
            ("99", "99 - Otro (Other)"),
        ],
        string="Tipo Identificación Extranjero",
        help="Type of identification for foreign customers",
    )
    dgi_pais_otro = fields.Char(
        string="País Otro",
        help="Full country name if country code is ZZ (not in DGI catalog)",
    )
    dgi_country_code = fields.Char(
        string="ISO Country Code",
        related="country_id.code",
        store=True,
    )
    dgi_allowed_tipo_ruc = fields.Char(compute="_compute_dgi_allowed_tipo_ruc")

    @api.depends("country_id", "country_id.code")
    def _compute_dgi_allowed_tipo_ruc(self):
        for partner in self:
            if partner.country_id and partner.country_id.code != "PA":
                partner.dgi_allowed_tipo_ruc = "04"
            else:
                partner.dgi_allowed_tipo_ruc = "01,02,03"

    @api.onchange("country_id")
    def _onchange_country_dgi_tipo_ruc(self):
        allowed = (self.dgi_allowed_tipo_ruc or "").split(",")
        if self.dgi_tipo_ruc and self.dgi_tipo_ruc not in allowed:
            self.dgi_tipo_ruc = allowed[0] if allowed else False

    @api.constrains("dgi_tipo_ruc", "country_id")
    def _check_dgi_tipo_ruc_country(self):
        for partner in self:
            if not partner.dgi_tipo_ruc:
                continue
            if partner.country_id and partner.country_id.code != "PA":
                if partner.dgi_tipo_ruc != "04":
                    raise ValidationError(
                        _(
                            "Foreign partners can only use Tipo RUC 04 (Foreign Entity)."
                        )
                    )
            elif partner.dgi_tipo_ruc == "04":
                raise ValidationError(
                    _("Tipo RUC 04 (Foreign Entity) cannot be used for a Panama partner.")
                )

    def _prepare_ruc_validation_vals(self, vals):
        """Always drop validation flags from client/ORM writes."""
        vals = dict(vals)
        vals.pop("dgi_ruc_validated", None)
        vals.pop("dgi_ruc_validation_date", None)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare_ruc_validation_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        return super().write(self._prepare_ruc_validation_vals(vals))

    @api.private
    def _dgi_set_ruc_validated(self, extra_vals=None):
        """Set RUC flags after a successful HKA ConsultaRucDv. Not RPC-callable."""
        vals = dict(extra_vals or {})
        vals["dgi_ruc_validated"] = True
        vals.setdefault("dgi_ruc_validation_date", fields.Datetime.now())
        return super().write(vals)

    @api.depends("dgi_ruc_validated", "dgi_tipo_ruc", "country_id", "country_id.code")
    def _compute_tipo_cliente_fe(self):
        """
        Compute tipoClienteFE based on RUC validation and country.
        01: Contribuyente (Taxpayer) - validated RUC in Panama
        02: Consumidor Final (Final Consumer) - not validated or no RUC
        03: Gobierno (Government) - tipo_ruc = 03
        04: Extranjero (Foreign) - country != PA
        """
        for partner in self:
            # Foreign customer
            if partner.country_id and partner.country_id.code != "PA":
                partner.dgi_tipo_cliente_fe = "04"
            # Government
            elif partner.dgi_tipo_ruc == "03":
                partner.dgi_tipo_cliente_fe = "03"
            # Taxpayer - validated RUC
            elif partner.dgi_ruc_validated and partner.vat:
                partner.dgi_tipo_cliente_fe = "01"
            # Final consumer - default
            else:
                partner.dgi_tipo_cliente_fe = "02"

    @api.depends("is_company", "dgi_tipo_cliente_fe")
    def _compute_tipo_contribuyente(self):
        """
        Compute tipoContribuyente.
        1: Natural (Individual)
        2: Jurídico (Legal Entity)
        Only applicable if not foreign (tipoClienteFE != 04)
        """
        for partner in self:
            if partner.dgi_tipo_cliente_fe == "04":
                # Not sent for foreign customers
                partner.dgi_tipo_contribuyente = False
            else:
                partner.dgi_tipo_contribuyente = "2" if partner.is_company else "1"

    def _validate_dgi_required_fields(self):
        """
        Validate required fields based on tipoClienteFE.
        Called when preparing DGI documents, not on every save.
        Raises UserError with detailed message if validation fails.
        """
        self.ensure_one()

        missing_fields = []

        if self.dgi_tipo_cliente_fe in ["01", "03"]:
            # Taxpayer or Government - RUC, DV, razón social, address, location required
            if not self.vat:
                missing_fields.append("RUC")
            if not self.dgi_dv:
                missing_fields.append("DV (Dígito Verificador)")
            if not self.dgi_razon_social and not self.name:
                missing_fields.append("Razón Social/Name")
            if not self.street:
                missing_fields.append("Address (Street)")
            if not self.l10n_pa_codigo_ubicacion:
                missing_fields.append("Código Ubicación")
            if not self.state_id:
                missing_fields.append("Province (State)")
            if not self.l10n_pa_distrito_id:
                missing_fields.append("District")
            if not self.l10n_pa_corregimiento_id:
                missing_fields.append("Corregimiento")

        elif self.dgi_tipo_cliente_fe == "04":
            # Foreign - identification type and number required
            if not self.dgi_tipo_identificacion_extranjero:
                missing_fields.append("Tipo Identificación")
            if not self.vat:
                missing_fields.append("Identification Number (VAT)")

        if missing_fields:
            raise UserError(
                _(
                    "Partner '%s' is missing required DGI fields:\n- %s\n\n"
                    "Please complete these fields before sending invoices to DGI."
                )
                % (self.name or self.display_name, "\n- ".join(missing_fields))
            )

    def action_validate_ruc(self):
        """Validate RUC with DGI via HKA API"""
        self.ensure_one()

        if not self.dgi_ruc:
            raise UserError(_("Please enter a RUC number first"))

        if self.dgi_tipo_ruc not in ["01", "02"]:
            raise UserError(
                _(
                    "Please select a valid Tipo RUC (01=Natural Person, 02=Juridical Person)"
                )
            )

        hka_api = self.env["l10n_pa_edi.hka_api"]
        result = hka_api.validate_ruc(
            self.dgi_ruc,
            self.dgi_tipo_ruc,
            company=self.company_id or self.env.company,
        )

        if not result.get("valid"):
            raise UserError(
                _("RUC validation failed: %s")
                % result.get("message", "Unknown error")
            )

        vals = {"vat": self.dgi_ruc}
        if result.get("dv"):
            vals["dgi_dv"] = result.get("dv")
        if result.get("tipo_ruc"):
            tipo_ruc_raw = result.get("tipo_ruc")
            if tipo_ruc_raw and len(str(tipo_ruc_raw)) != 2:
                tipo_ruc_raw = str(tipo_ruc_raw).zfill(2)
            vals["dgi_tipo_ruc"] = tipo_ruc_raw
        if result.get("razonSocial"):
            vals["dgi_razon_social"] = result.get("razonSocial")
            if not self.name:
                vals["name"] = result.get("razonSocial")
        if result.get("status"):
            vals["dgi_taxpayer_status"] = result.get("status")

        self._dgi_set_ruc_validated(vals)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("RUC %s validated successfully. DV: %s")
                % (self.dgi_ruc, vals.get("dgi_dv", "N/A")),
                "type": "success",
                "sticky": False,
            },
        }

    def _format_panama_phone_for_dgi(self, phone_number):
        """
        Format phone number for DGI Panama API.
        Odoo stores phones as +507 000-0000 or +507 0000-0000
        DGI expects: 000-0000 (7 digits) or 0000-0000 (8 digits)
        
        Returns formatted number without country code, or empty string.
        """
        if not phone_number:
            return ""

        # Remove country code (+507) and all non-digit characters
        # Odoo formats: "+507 263-1234" or "+507 6234-5678"
        digits_only = ''.join(filter(str.isdigit, phone_number))

        # Remove Panama country code (507) if present at the start
        if digits_only.startswith('507') and len(digits_only) > 3:
            digits_only = digits_only[3:]

        # Format based on length
        if len(digits_only) == 7:
            # Landline format: 000-0000
            return f"{digits_only[:3]}-{digits_only[3:]}"
        elif len(digits_only) == 8:
            # Mobile format: 0000-0000
            return f"{digits_only[:4]}-{digits_only[4:]}"
        else:
            # Return as-is if not standard Panama format
            return digits_only if digits_only else ""

    def _prepare_dgi_cliente_data(self):
        """
        Prepare partner data for HKA API Cliente structure.
        Complies with DGI Panama electronic invoice requirements.
        """
        self.ensure_one()

        # Validate required fields before preparing data
        self._validate_dgi_required_fields()

        tipo_cliente_fe = self.dgi_tipo_cliente_fe or "02"

        # Format phone numbers for DGI (removes +507 and formats)
        phone1 = ""
        phone2 = ""
        if self.country_id and self.country_id.code == "PA":
            phone1 = self._format_panama_phone_for_dgi(self.phone)
            phone2 = self._format_panama_phone_for_dgi(self.mobile)
        else:
            phone1 = self.phone or ""
            phone2 = self.mobile or ""

        # Get country code - use ZZ if country not in DGI catalog
        pais_code = ""
        if self.country_id and self.country_id.dgi_code_id:
            pais_code = self.country_id.dgi_code_id.code or "ZZ"
        elif self.country_id:
            pais_code = "ZZ"

        # HKA: omit fields that must not be sent (empty string is still "sent").
        client_vals = {
            "tipoClienteFE": tipo_cliente_fe,
            "pais": pais_code,
        }
        if phone1:
            client_vals["telefono1"] = phone1[:16]
        if self.email:
            client_vals["correoElectronico1"] = self.email[:50]

        if pais_code == "ZZ":
            pais_otro = (
                self.dgi_pais_otro or (self.country_id.name if self.country_id else "")
            )[:50]
            if pais_otro:
                client_vals["paisOtro"] = pais_otro

        if tipo_cliente_fe in ["01", "03"]:
            client_vals.update(
                {
                    "tipoContribuyente": self.dgi_tipo_contribuyente or "1",
                    "numeroRUC": (self.vat or "")[:20],
                    "digitoVerificadorRUC": (self.dgi_dv or "").strip().zfill(2)[:2],
                    "razonSocial": (self.dgi_razon_social or self.name or "")[:200],
                    "direccion": (
                        " ".join(filter(None, [self.street or "", self.street2 or ""]))
                    )[:100],
                    "codigoUbicacion": (self.l10n_pa_codigo_ubicacion or "")[:8],
                    "provincia": (self.state_id.name if self.state_id else "")[:50],
                    "distrito": (
                        self.l10n_pa_distrito_id.name
                        if self.l10n_pa_distrito_id
                        else ""
                    )[:50],
                    "corregimiento": (
                        self.l10n_pa_corregimiento_id.name
                        if self.l10n_pa_corregimiento_id
                        else ""
                    )[:50],
                }
            )
        elif tipo_cliente_fe == "02":
            if self.name:
                client_vals["razonSocial"] = self.name[:200]
            if self.vat:
                client_vals["numeroRUC"] = self.vat[:20]
        elif tipo_cliente_fe == "04":
            client_vals["tipoIdentificacion"] = (
                self.dgi_tipo_identificacion_extranjero or "01"
            )
            if self.vat:
                client_vals["nroIdentificacionExtranjero"] = self.vat[:50]
            if self.dgi_tipo_identificacion_extranjero == "01" and self.country_id:
                client_vals["paisExtranjero"] = (self.country_id.name or "")[:50]

        return {key: value for key, value in client_vals.items() if value}
