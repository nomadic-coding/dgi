# -*- coding: utf-8 -*-

"""HKA Enviar combinations that DGI accepts.

Rules from https://felwiki.thefactoryhka.com.pa/enviar and the DGI ficha técnica:
- tipoDocumento 01/09 stay in Panama (destino 1, pais PA)
- tipoDocumento 03/10 are foreign (destino 2, pais not PA)
- tipoVenta is only sent on sales, never on credit/debit notes
- tipoOperacion 2 is a purchase/import entry, not a customer sale
- formatoCAFE and entregaCAFE are independent 1|2|3 fields
- tipoEmision 03/04 (post authorization) are not offered; leftover values snap to 01
- tipoEmision 02 requires contingency date and reason
- formaPago 99 requires a description
"""

HKA_TIPO_DOCUMENTO_BY_MOVE = {
    "out_invoice": ("01", "03", "08", "09", "10"),
    "out_refund": ("04", "06"),
}

HKA_NATURALEZA_BY_DOCUMENT = {
    "01": ("01", "10", "12", "13", "14"),
    "02": ("21",),
    "03": ("02", "03"),
    "04": ("11",),
    "05": ("01",),
    "06": ("11",),
    "07": ("01",),
    "08": ("01", "02", "10", "12", "13", "14"),
    "09": ("01", "10"),
    "10": ("04",),
}

HKA_DESTINO_BY_DOCUMENT = {
    "01": ("1",),
    "02": ("2",),
    "03": ("2",),
    "04": ("1", "2"),
    "05": ("1", "2"),
    "06": ("1", "2"),
    "07": ("1", "2"),
    "08": ("1", "2"),
    "09": ("1",),
    "10": ("2",),
}

HKA_TIPO_OPERACION_BY_DOCUMENT = {
    "01": ("1",),
    "02": ("2",),
    "03": ("1",),
    "04": ("1",),
    "05": ("1",),
    "06": ("1",),
    "07": ("1",),
    "08": ("1",),
    "09": ("1",),
    "10": ("1",),
}

HKA_TIPO_VENTA_DOCUMENTS = frozenset({"01", "03", "08", "09", "10"})
HKA_CONTINGENCY_EMISSION = frozenset({"02"})
HKA_POSTERIOR_EMISSION = frozenset({"03", "04"})
HKA_DGI_TAB_FIELDS = frozenset({
    "hka_tipo_emision",
    "hka_fecha_inicio_contingencia",
    "hka_motivo_contingencia",
    "hka_tipo_documento",
    "hka_tipo_documento_manual",
    "hka_naturaleza_operacion",
    "hka_tipo_operacion",
    "hka_destino_operacion",
    "hka_forma_pago",
    "hka_desc_forma_pago",
    "hka_tipo_venta",
    "hka_merge_same_dgi_code",
    "hka_tipo_sucursal",
    "hka_formato_cafe",
    "hka_entrega_cafe",
    "hka_envio_contenedor",
    "hka_proceso_generacion",
})
HKA_MOTIVO_CONTINGENCIA_MIN = 15
HKA_ANULACION_MAX_HOURS = 182
HKA_ENTREGA_CAFE = ("1", "2", "3")
HKA_COMBO_WRITE_FIELDS = frozenset({
    "hka_tipo_documento",
    "hka_tipo_documento_manual",
    "hka_naturaleza_operacion",
    "hka_destino_operacion",
    "hka_tipo_operacion",
    "hka_tipo_venta",
    "hka_formato_cafe",
    "hka_entrega_cafe",
    "hka_tipo_emision",
    "hka_fecha_inicio_contingencia",
    "hka_motivo_contingencia",
    "hka_forma_pago",
    "hka_desc_forma_pago",
    "move_type",
    "partner_id",
    "journal_id",
})


def allowed_document_types(move_type, partner_country_code=None):
    """Document types valid for this move and receiver country."""
    allowed = HKA_TIPO_DOCUMENTO_BY_MOVE.get(move_type, ())
    if not partner_country_code:
        return allowed
    if partner_country_code != "PA":
        return tuple(
            code
            for code in allowed
            if "2" in HKA_DESTINO_BY_DOCUMENT.get(code, ())
        )
    return tuple(
        code for code in allowed if "1" in HKA_DESTINO_BY_DOCUMENT.get(code, ())
    )


def allowed_entrega_cafe(_formato_cafe=None):
    return HKA_ENTREGA_CAFE


def default_destino(allowed_destinos, partner_country_code=None):
    if partner_country_code and partner_country_code != "PA" and "2" in allowed_destinos:
        return "2"
    if allowed_destinos:
        return allowed_destinos[0]
    return "1"
