# -*- coding: utf-8 -*-

import logging
import time
from datetime import datetime, timedelta

import requests
from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HkaApi(models.AbstractModel):
    """HKA API Client for Panama Electronic Invoicing"""

    _name = "l10n_pa_edi.hka_api"
    _description = "HKA API Client"

    @api.model
    def _auto_map_defaults(self):
        """Idempotent catalog/tax mapping, also run on module update."""
        from odoo.addons.l10n_pa_edi.hooks import (
            _auto_map_dgi_catalogs,
            _auto_map_l10n_pa_taxes,
        )

        _auto_map_dgi_catalogs(self.env)
        _auto_map_l10n_pa_taxes(self.env)

    @api.model
    def _company_from_move(self, move_id=None):
        if move_id:
            move = self.env["account.move"].browse(move_id)
            if move.exists():
                return move.company_id
        return self.env.company

    @api.model
    def _get_company(self, company=None):
        return (company or self.env.company).sudo()

    @api.model
    def _get_config(self, company=None):
        """Get HKA configuration from the company (not database-wide ICP)."""
        company = self._get_company(company)
        return {
            "api_url": company.hka_api_url or "",
            "usuario": company.hka_usuario or "",
            "clave": company.hka_clave or "",
            "timeout": int(company.hka_timeout or 30),
            "verify_ssl": bool(company.hka_verify_ssl),
        }

    @api.model
    def _get_access_token(self, company=None):
        """Get a JWT cached on the company, or authenticate for a new one."""
        company = self._get_company(company)
        token = company.hka_auth_token or ""
        expiry_str = company.hka_auth_token_expiry or ""

        if token and expiry_str:
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if expiry > datetime.now():
                    _logger.debug("Using cached HKA token for company %s", company.id)
                    return token
            except ValueError:
                pass

        _logger.info("Authenticating with HKA to get new JWT token")
        token = self._authenticate(company=company)

        expiry = datetime.now() + timedelta(minutes=55)
        company.write({
            "hka_auth_token": token,
            "hka_auth_token_expiry": expiry.isoformat(),
        })

        return token

    @api.model
    def _authenticate(self, company=None):
        """
        Authenticate with HKA API to obtain JWT token

        HKA authentication pattern (from API docs):
        POST /api/Autenticacion
        Header: Authorization: {usuario} (NOT Bearer)
        Body: {"usuario": "{usuario}", "clave": "{clave}"}

        Returns: JWT token as string
        """
        config = self._get_config(company=company)
        auth_url = f"{config['api_url'].rstrip('/')}/api/Autenticacion"

        # During authentication, Authorization header is just the usuario (no "Bearer")
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": config["usuario"],
        }

        data = {
            "usuario": config["usuario"],
            "clave": config["clave"],
        }

        _logger.info(
            "Authenticating with HKA API for user: %s", config["usuario"][:10] + "..."
        )

        try:
            response = requests.post(
                auth_url,
                headers=headers,
                json=data,
                timeout=config["timeout"],
                verify=config["verify_ssl"],
            )
            response.raise_for_status()

            # HKA returns JWT token - try multiple extraction methods
            auth_token = None
            try:
                result = response.json()
                if isinstance(result, str):
                    auth_token = result
                elif isinstance(result, dict):
                    # Try different possible token field names
                    auth_token = (
                        result.get("token")
                        or result.get("access_token")
                        or result.get("authToken")
                        or result.get("jwt")
                        or (
                            result.get("data", {}).get("token")
                            if isinstance(result.get("data"), dict)
                            else None
                        )
                    )
            except ValueError:
                # Response is not JSON, might be plain text token
                auth_token = response.text.strip()

            if not auth_token or not isinstance(auth_token, str):
                _logger.error("Authentication response: %s", response.text[:500])
                raise UserError(
                    _("Authentication successful but no valid JWT token received")
                )

            _logger.info("HKA authentication successful, JWT token received")
            return auth_token

        except requests.exceptions.HTTPError as exc:
            error_msg = _("HKA Authentication failed (HTTP %s): %s") % (
                response.status_code,
                response.text[:200],
            )
            _logger.error(error_msg)
            raise UserError(error_msg) from exc
        except Exception as exc:
            error_msg = _("HKA Authentication error: %s") % str(exc)
            _logger.exception(error_msg)
            raise UserError(error_msg) from exc

    @api.model
    def _make_request(self, endpoint, method="POST", data=None, company=None):
        """
        Make HTTP request to HKA API

        For API requests (after authentication), use Bearer token format

        Returns:
            tuple: (http_status_code, response_data)
        """
        config = self._get_config(company=company)
        token = self._get_access_token(company=company)

        url = f"{config['api_url'].rstrip('/')}/{endpoint.lstrip('/')}"

        # For API requests, use "Bearer {token}" format (different from authentication)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

        _logger.info("HKA API Request: %s %s", method, url)

        try:
            if method == "GET":
                response = requests.get(
                    url,
                    headers=headers,
                    params=data,
                    timeout=config["timeout"],
                    verify=config["verify_ssl"],
                )
            elif method == "POST":
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=config["timeout"],
                    verify=config["verify_ssl"],
                )
            elif method == "PUT":
                response = requests.put(
                    url,
                    headers=headers,
                    json=data,
                    timeout=config["timeout"],
                    verify=config["verify_ssl"],
                )
            elif method == "DELETE":
                response = requests.delete(
                    url,
                    headers=headers,
                    timeout=config["timeout"],
                    verify=config["verify_ssl"],
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Log response
            _logger.info(
                "HKA API Response: %s - %s", response.status_code, response.text[:500]
            )

            response.raise_for_status()

            # Return both status code and response data
            if response.content:
                return response.status_code, response.json()
            else:
                return response.status_code, {}

        except requests.exceptions.HTTPError as exc:
            # Return status code even on HTTP errors
            status_code = response.status_code if "response" in locals() else None
            error_msg = _("HKA API request failed (HTTP %s): %s") % (
                status_code,
                response.text[:200] if "response" in locals() else str(exc),
            )
            _logger.error(error_msg)
            raise UserError(error_msg) from exc
        except Exception as exc:
            error_msg = _("HKA API request error: %s") % str(exc)
            _logger.exception(error_msg)
            raise UserError(error_msg) from exc

    @api.model
    def validate_ruc(self, ruc, tipo_ruc="02"):
        """
        Validate RUC with DGI via HKA API

        API: POST /api/ConsultaRucDv
        Doc: https://felwiki.thefactoryhka.com.pa/consultarucdv_english

        Args:
            ruc: RUC number (e.g., "E-8-182965")
            tipo_ruc: Type of taxpayer ("01"=Person, "02"=Business)

        Returns:
            dict with validation result
        """
        data = {
            "tipoRuc": str(tipo_ruc),
            "ruc": str(ruc),
        }

        start_time = time.time()
        response = None
        http_status_code = None
        status = "error"
        error_message = None
        result = {"valid": False, "ruc": ruc}

        try:
            _logger.info("Validating RUC %s with HKA API", ruc)
            http_status_code, response = self._make_request(
                "api/ConsultaRucDv",
                method="POST",
                data=data,
                company=self.env.company,
            )

            codigo = response.get("codigo", "")
            is_valid = codigo == "200"
            info_ruc = response.get("infoRuc", {})
            status = "success"

            result = {
                "valid": is_valid,
                "tipo_ruc": info_ruc.get("tipoRuc", ""),
                "razonSocial": info_ruc.get("razonSocial", ""),
                "ruc": info_ruc.get("ruc", ""),
                "dv": info_ruc.get("dv", ""),
                "status": info_ruc.get("afiliadoFE", ""),
                "message": response.get("mensaje", ""),
                "codigo": codigo,
            }

        except Exception as exc:
            _logger.error("RUC validation failed: %s", str(exc))
            error_message = str(exc)
            result = {
                "valid": False,
                "message": str(exc),
                "ruc": ruc,
            }

        finally:
            # Log API call (automatically uses new cursor to survive transaction rollback)
            duration = (time.time() - start_time) * 1000  # Convert to ms
            self.env["hka.api.log"].log_api_call(
                api_method="consulta_ruc_dv",
                request_data=data,
                response_data=response or result,
                status=status,
                error_message=error_message,
                http_status_code=http_status_code,
                duration_ms=duration,
            )

        return result

    @api.model
    def enviar(self, document_data, move_id=None):
        """
        Send electronic document to DGI via HKA API

        API: POST /api/Enviar
        Doc: https://felwiki.thefactoryhka.com.pa/enviar_english

        Args:
            document_data: dict with documento structure
            move_id: ID of related account.move (invoice)

        Returns:
            dict with structured result:
            {
                "success": bool,
                "status": str,  # DGI status/resultado or error indicator
                "error_message": str or False,
                "dgi_cufe": str or False,
                "dgi_qr": str or False,
                "dgi_fecha_recepcion": str or False,
                "dgi_protocolo_autorizacion": str or False,
                "codigo": str,  # DGI response code
                "mensaje": str,  # DGI response message
            }
        """
        start_time = time.time()
        response = None
        http_status_code = None
        status = "error"
        error_message = None
        result = {
            "success": False,
            "status": "Exception",
            "error_message": False,
            "dgi_cufe": False,
            "dgi_qr": False,
            "dgi_fecha_recepcion": False,
            "dgi_protocolo_autorizacion": False,
            "codigo": "",
            "mensaje": "",
        }

        try:
            _logger.info("Sending electronic document to HKA API")
            http_status_code, response = self._make_request(
                "api/Enviar",
                method="POST",
                data=document_data,
                company=self._company_from_move(move_id),
            )

            # Parse response
            codigo = response.get("codigo", "")
            resultado = response.get("resultado", "")
            mensaje = response.get("mensaje", "")

            # Check if API returned success code
            if codigo == "200":
                status = "success"
                result = {
                    "success": True,
                    "status": resultado,
                    "error_message": False,
                    "dgi_cufe": response.get("cufe", "") or False,
                    "dgi_qr": response.get("qr", "") or False,
                    "dgi_fecha_recepcion": response.get("fechaRecepcionDGI", "")
                    or False,
                    "dgi_protocolo_autorizacion": response.get(
                        "nroProtocoloAutorizacion", ""
                    )
                    or False,
                    "codigo": codigo,
                    "mensaje": mensaje,
                }
            else:
                # API returned error code
                status = "error"
                error_message = f"Code: {codigo}, Message: {mensaje}"
                result = {
                    "success": False,
                    "status": resultado or f"Error: {codigo}",
                    "error_message": error_message,
                    "dgi_cufe": response.get("cufe", "") or False,
                    "dgi_qr": response.get("qr", "") or False,
                    "dgi_fecha_recepcion": response.get("fechaRecepcionDGI", "")
                    or False,
                    "dgi_protocolo_autorizacion": response.get(
                        "nroProtocoloAutorizacion", ""
                    )
                    or False,
                    "codigo": codigo,
                    "mensaje": mensaje,
                }

        except Exception as exc:
            _logger.exception("Failed to send electronic document")
            error_message = str(exc)
            result = {
                "success": False,
                "status": "Exception",
                "error_message": error_message,
                "dgi_cufe": False,
                "dgi_qr": False,
                "dgi_fecha_recepcion": False,
                "dgi_protocolo_autorizacion": False,
                "codigo": "",
                "mensaje": str(exc),
            }

        finally:
            # Log API call (automatically uses new cursor to survive transaction rollback)
            duration = (time.time() - start_time) * 1000  # Convert to ms
            self.env["hka.api.log"].log_api_call(
                api_method="enviar",
                request_data=document_data,
                response_data=response,
                status=status,
                error_message=error_message,
                http_status_code=http_status_code,
                duration_ms=duration,
                move_id=move_id,
            )

        return result

    @api.model
    def anular(self, anulacion_data, move_id=None):
        """
        Cancel electronic invoice in DGI via HKA API

        API: POST /api/Anular
        Doc: https://felwiki.thefactoryhka.com.pa/anular_english

        Args:
            anulacion_data: dict with cancellation structure:
                {
                    "motivoAnulacion": "string",
                    "datosDocumento": {
                        "codigoSucursalEmisor": "string",
                        "numeroDocumentoFiscal": "string",
                        "puntoFacturacionFiscal": "string",
                        "serialDispositivo": "string",
                        "tipoDocumento": "string",
                        "tipoEmision": "string"
                    }
                }
            move_id: ID of related account.move (invoice)

        Returns:
            dict with result:
            {
                "success": bool,
                "status": str,
                "error_message": str or False,
                "codigo": str,
                "mensaje": str,
            }
        """
        start_time = time.time()
        response = None
        http_status_code = None
        status = "error"
        error_message = None

        result = {
            "success": False,
            "status": "Exception",
            "error_message": False,
            "codigo": "",
            "mensaje": "",
        }

        try:
            _logger.info("Canceling electronic document via HKA API")
            http_status_code, response = self._make_request(
                "api/Anulacion",
                method="POST",
                data=anulacion_data,
                company=self._company_from_move(move_id),
            )

            # Parse response
            codigo = response.get("codigo", "")
            resultado = response.get("resultado", "")
            mensaje = response.get("mensaje", "")

            # Check if API returned success code
            if codigo == "200":
                status = "success"
                result = {
                    "success": True,
                    "status": resultado or "Anulado",
                    "error_message": False,
                    "codigo": codigo,
                    "mensaje": mensaje,
                }
            else:
                # API returned error code
                status = "error"
                error_message = f"Code: {codigo}, Message: {mensaje}"
                result = {
                    "success": False,
                    "status": resultado or f"Error: {codigo}",
                    "error_message": error_message,
                    "codigo": codigo,
                    "mensaje": mensaje,
                }

        except Exception as exc:
            _logger.exception("Failed to cancel electronic document")
            error_message = str(exc)
            result = {
                "success": False,
                "status": "Exception",
                "error_message": error_message,
                "codigo": "",
                "mensaje": str(exc),
            }

        finally:
            # Log API call (automatically uses new cursor to survive transaction rollback)
            duration = (time.time() - start_time) * 1000  # Convert to ms
            self.env["hka.api.log"].log_api_call(
                api_method="anular",
                request_data=anulacion_data,
                response_data=response,
                status=status,
                error_message=error_message,
                http_status_code=http_status_code,
                duration_ms=duration,
                move_id=move_id,
            )

        return result

    @api.model
    def descargar(self, cufe, numero_documento, tipo_archivo="pdf", move_id=None):
        """
        Download electronic invoice from DGI via HKA API

        API: POST /api/Descarga
        Doc: https://felwiki.thefactoryhka.com.pa/descarga_english

        Args:
            cufe: CUFE code from the invoice
            numero_documento: Document number
            tipo_archivo: File type ("PDF" or "XML")
            move_id: ID of related account.move (invoice)

        Returns:
            dict with result:
            {
                "success": bool,
                "file_content": bytes or False,  # Base64 decoded content
                "file_name": str,
                "error_message": str or False,
            }
        """
        start_time = time.time()
        response = None
        http_status_code = None
        status = "error"
        error_message = None

        data = {
            "cufe": cufe,
            "tipoArchivo": tipo_archivo.upper(),
        }

        result = {
            "success": False,
            "file_content": False,
            "file_name": f"{numero_documento}.{tipo_archivo}",
            "error_message": False,
        }

        try:
            _logger.info("Downloading e-invoice from HKA API: %s", numero_documento)
            http_status_code, response = self._make_request(
                "api/Descarga",
                method="POST",
                data=data,
                company=self._company_from_move(move_id),
            )

            # Check if download was successful
            codigo = response.get("Codigo", "")
            resultado = response.get("Resultado", False)
            if resultado == "Procesado":
                status = "success"
                # Get the file content (usually base64 encoded)
                file_content = response.get("Archivo", "")
                if file_content:
                    import base64

                    result = {
                        "success": True,
                        "file_content": base64.b64decode(file_content),
                        "file_name": f"{numero_documento}.{tipo_archivo}",
                        "error_message": False,
                    }
                else:
                    status = "error"
                    error_message = "No file content in response"
                    result["error_message"] = error_message
            else:
                # API returned error code
                status = "error"
                mensaje = response.get("Mensaje", "Unknown error")
                error_message = f"Code: {codigo}, Message: {mensaje}"
                result["error_message"] = error_message

        except Exception as exc:
            _logger.exception("Failed to download electronic document")
            error_message = str(exc)
            result["error_message"] = error_message

        finally:
            # Log API call (automatically uses new cursor to survive transaction rollback)
            duration = (time.time() - start_time) * 1000  # Convert to ms
            self.env["hka.api.log"].log_api_call(
                api_method="descarga",
                request_data=data,
                response_data=response,
                status=status,
                error_message=error_message,
                http_status_code=http_status_code,
                duration_ms=duration,
                move_id=move_id,
            )

        return result
