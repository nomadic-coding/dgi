# -*- coding: utf-8 -*-

import logging
from collections import defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo.tools.mail import html2plaintext

from odoo.addons.l10n_pa_edi.models.hka_combinations import (
    HKA_CONTINGENCY_EMISSION,
    HKA_TIPO_VENTA_DOCUMENTS,
)

_logger = logging.getLogger(__name__)

HKA_ITBMS_RATES = {
    "00": 0.0,
    "01": 0.07,
    "02": 0.10,
    "03": 0.15,
}


class L10nPaEdiPayload(models.AbstractModel):
    _name = "l10n.pa.edi.payload"
    _description = "Panama HKA Enviar payload"

    def _format_dgi_datetime(self, date_value):
        """Format a date/datetime as DGI ISO 8601 with Panama timezone (UTC-5)."""
        if not date_value:
            date_value = fields.Date.today()
        if not isinstance(date_value, datetime):
            date_value = datetime.combine(date_value, time.min)
        return date_value.strftime('%Y-%m-%dT%H:%M:%S-05:00')

    def _prepare_dgi_informacion_interes(self, move):
        """Plain text for HKA (narration is HTML); line breaks as U+2028 LINE SEPARATOR."""
        move.ensure_one()
        line_sep = '\u2028'
        parts = []
        ref = (move.ref or '').strip()
        narration = (move.narration or '').strip()
        if ref:
            parts.append('Customer Reference: ' + html2plaintext(ref).strip())
        if narration:
            marked = narration.replace('</p>', '</p>\n').replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
            parts.append(html2plaintext(marked).strip())
        if not parts:
            return ''
        plain = '\n\n'.join((p for p in parts if p))
        plain = plain.replace('\r\n', '\n').replace('\r', '\n')
        plain = plain.replace('\n', line_sep)
        return plain.strip()[:5000]

    def _hka_normalize_lista_item_descripcion(self, raw, max_len=500, truncate=True):
        """Description text for listaItems; newlines -> U+2028 (invoice line names are plain)."""
        if not raw:
            return ''
        plain = str(raw).strip()
        if not plain:
            return ''
        plain = plain.replace('\r\n', '\n').replace('\r', '\n')
        plain = plain.replace('\n', '\u2028')
        if truncate and max_len:
            return plain[:max_len]
        return plain

    def _hka_itbms_amount_from_base(self, move, precio_item, tasa):
        """HKA validates valorITBMS against precioItem * official ITBMS rate."""
        rate = HKA_ITBMS_RATES.get(tasa or '00', 0.0)
        return move.currency_id.round(float(precio_item) * rate)

    def _hka_sync_item_valor_total(self, move, item):
        """valorTotal must match precioItem + valorITBMS + valorISC (HKA)."""
        base = float(item['precioItem'])
        itbms = float(item.get('valorITBMS') or 0)
        isc = float(item.get('valorISC') or 0)
        item['valorTotal'] = '{:.2f}'.format(move.currency_id.round(base + itbms + isc))

    def _hka_parse_tax_totals_for_hka(self, move, tax_totals_dict):
        """Read Odoo tax_totals: merge groups by ITBMS tasa (00–03) / ISC rate, signed amounts.

        ITBMS: merged by tasa. ISC (04): merged by ``hka_tax_isc_id.rate`` (same tasaISC on HKA),
        so multiple taxes pointing at the same rate share one consolidated row.
        """
        move.ensure_one()
        itbms_acc = defaultdict(lambda: [0.0, 0.0])
        isc_acc = defaultdict(lambda: [0.0, 0.0])
        unmapped = []
        if not isinstance(tax_totals_dict, dict) or not tax_totals_dict:
            return {'itbms_rows': [], 'isc_rows': [], 'total_itbms': 0.0, 'total_isc': 0.0}
        for subtotal in tax_totals_dict.get('subtotals') or []:
            for tg in subtotal.get('tax_groups') or []:
                involved = tg.get('involved_tax_ids') or []
                base = float(tg.get('base_amount_currency') or 0.0)
                tax_amt = float(tg.get('tax_amount_currency') or 0.0)
                if move.currency_id.is_zero(base) and move.currency_id.is_zero(tax_amt):
                    continue
                tax = None
                for tid in involved:
                    t = self.env['account.tax'].browse(tid)
                    if t and t.exists() and t.hka_tax_code:
                        tax = t
                        break
                if not tax:
                    label = tg.get('group_name') or tg.get('tax_group_name') or _('Unknown tax group')
                    unmapped.append(_("Tax group '%(label)s' has no tax with an HKA code (base=%(base).2f, tax=%(tax).2f)") % {'label': label, 'base': base, 'tax': tax_amt})
                    continue
                code = tax.hka_tax_code
                if code in ('00', '01', '02', '03'):
                    itbms_acc[code][0] += base
                    itbms_acc[code][1] += tax_amt
                elif code == '04':
                    if not tax.hka_tax_isc_id:
                        unmapped.append(_("ISC tax '%s' is missing HKA ISC rate configuration") % tax.display_name)
                        continue
                    base_isc = float(tg.get('base_amount_currency') or 0.0)
                    if move.currency_id.is_zero(base_isc):
                        disp_base = tg.get('display_base_amount_currency')
                        if disp_base is not False and disp_base is not None:
                            base_isc = float(disp_base or 0.0)
                    rate_key = round(float(tax.hka_tax_isc_id.rate), 6)
                    isc_acc[rate_key][0] += base_isc
                    isc_acc[rate_key][1] += tax_amt
                else:
                    unmapped.append(_("Tax '%s' uses unsupported HKA code '%s'") % (tax.display_name, code))
        if unmapped:
            raise UserError(_('Cannot build HKA payload — fix tax mapping:\n%s') % '\n'.join(('- %s' % m for m in unmapped)))
        itbms_rows = [(tasa, move.currency_id.round(pair[0]), move.currency_id.round(pair[1])) for tasa, pair in sorted(itbms_acc.items())]
        isc_rows = [(rate_key, move.currency_id.round(pair[0]), move.currency_id.round(pair[1])) for rate_key, pair in sorted(isc_acc.items(), key=lambda kv: kv[0])]
        total_itbms = move.currency_id.round(sum((t for _, _, t in itbms_rows)))
        total_isc = move.currency_id.round(sum((t for _, _, t in isc_rows)))
        return {'itbms_rows': itbms_rows, 'isc_rows': isc_rows, 'total_itbms': total_itbms, 'total_isc': total_isc}

    def _hka_validate_consolidated_items(self, move, items, tax_parsed):
        """Ensure consolidated listaItems match the move after rounding adjustments."""
        move.ensure_one()
        if not items:
            raise UserError(_('Cannot send to DGI: consolidated invoice has no line items.'))
        cur = move.currency_id
        rnd = cur.rounding or 0.01
        sum_b = cur.round(sum((float(x['precioItem']) for x in items)))
        sum_ib = cur.round(sum((float(x.get('valorITBMS') or 0) for x in items)))
        sum_isc = cur.round(sum((float(x.get('valorISC') or 0) for x in items)))
        sum_tot = cur.round(sum((float(x['valorTotal']) for x in items)))
        if move.move_type == 'out_invoice':
            for it in items:
                b = float(it['precioItem'])
                if float_compare(b, 0.0, precision_rounding=rnd) < 0:
                    raise UserError(_('Cannot send this customer invoice to DGI: consolidated detail has negative net amount (%(amt).2f). Check down payment / tax lines.') % {'amt': b})
        checks = [(sum_b, move.amount_untaxed, _('untaxed total')), (sum_ib, tax_parsed['total_itbms'], _('ITBMS')), (sum_isc, tax_parsed['total_isc'], _('ISC')), (sum_tot, move.amount_total, _('total with tax'))]
        for a, b, label in checks:
            if float_compare(a, b, precision_rounding=rnd) != 0:
                raise UserError(_('HKA consolidated payload does not match invoice %(label)s: payload=%(a).2f, move=%(b).2f') % {'label': label, 'a': a, 'b': b})

    def _hka_itbms_net_per_tasa_from_lines(self, move, product_lines):
        """Signed net ITBMS per HKA tasa (00–03) across all product lines (+ and - qty)."""
        move.ensure_one()
        per_tasa = defaultdict(float)
        for line in product_lines:
            if not line.tax_ids:
                continue
            base_line = move._prepare_product_base_line_for_taxes_computation(line)
            self.env['account.tax']._add_tax_details_in_base_line(base_line, move.company_id)
            for tax_data in base_line.get('tax_details', {}).get('taxes_data', []):
                tax = tax_data.get('tax')
                if tax and tax.hka_tax_code in ('00', '01', '02', '03'):
                    per_tasa[tax.hka_tax_code] += tax_data.get('raw_tax_amount_currency', 0.0)
        return dict(per_tasa)

    def _hka_reconcile_lista_items_itbms(self, move, lista_items, product_lines, total_itbms_invoice):
        """Per tasaITBMS: spread valorITBMS so each group matches net ITBMS on the move."""
        move.ensure_one()
        net_per_tasa = self._hka_itbms_net_per_tasa_from_lines(move, product_lines)
        by_tasa = defaultdict(list)
        for it in lista_items:
            if 'valorITBMS' in it and 'tasaITBMS' in it:
                by_tasa[it['tasaITBMS']].append(it)
        for tasa, items_g in by_tasa.items():
            target = move.currency_id.round(net_per_tasa.get(tasa, 0.0))
            sum_g = sum((float(it['valorITBMS']) for it in items_g))
            if abs(move.currency_id.round(sum_g - target)) <= 0.005:
                for it in items_g:
                    self._hka_sync_item_valor_total(move, it)
                continue
            if abs(target) <= 0.005:
                for it in items_g:
                    it['valorITBMS'] = '{:.2f}'.format(0.0)
                    self._hka_sync_item_valor_total(move, it)
                continue
            if sum_g <= 0:
                for it in items_g:
                    self._hka_sync_item_valor_total(move, it)
                continue
            acc = 0.0
            for idx, it in enumerate(items_g):
                t = float(it['valorITBMS'])
                if idx == len(items_g) - 1:
                    v = move.currency_id.round(target - acc)
                else:
                    v = move.currency_id.round(t * target / sum_g)
                    acc += v
                it['valorITBMS'] = '{:.2f}'.format(v)
            for it in items_g:
                self._hka_sync_item_valor_total(move, it)
        items_with = [it for it in lista_items if 'valorITBMS' in it]
        if not items_with:
            return
        sum_lines = sum((float(it['valorITBMS']) for it in items_with))
        rem = move.currency_id.round(sum_lines - total_itbms_invoice)
        if abs(rem) > 0.005:
            last = items_with[-1]
            last['valorITBMS'] = '{:.2f}'.format(move.currency_id.round(float(last['valorITBMS']) - rem))
            self._hka_sync_item_valor_total(move, last)

    def _hka_itbms_tasa_for_line(self, move, line):
        """First ITBMS HKA tasa (00–03) on the line's taxes; default 00 if none."""
        move.ensure_one()
        for tax in line.tax_ids:
            if tax.hka_tax_code in ('00', '01', '02', '03'):
                return tax.hka_tax_code
        return '00'

    def _hka_group_item_lines_by_itbms_tasa(self, move, item_lines):
        """Positive product lines bucketed by their ITBMS HKA code."""
        buckets = defaultdict(lambda: self.env['account.move.line'])
        for line in item_lines:
            tasa = self._hka_itbms_tasa_for_line(move, line)
            buckets[tasa] |= line
        return buckets

    def _hka_group_item_lines_by_isc_rate(self, move, item_lines):
        """Positive lines that carry ISC (04), keyed by rounded ``hka_tax_isc_id.rate`` (tasaISC)."""
        buckets = defaultdict(lambda: self.env['account.move.line'])
        for line in item_lines:
            for tax in line.tax_ids:
                if tax.hka_tax_code == '04' and tax.hka_tax_isc_id:
                    rate_key = round(float(tax.hka_tax_isc_id.rate), 6)
                    buckets[rate_key] |= line
                    break
        return buckets

    def _hka_isc_base_per_rate_from_lines(self, move, product_lines):
        """Per rounded tasaISC: sum of Odoo ISC bases (``raw_base_amount_currency``) on product lines."""
        move.ensure_one()
        per_rate = defaultdict(float)
        for line in product_lines:
            if not line.tax_ids:
                continue
            base_line = move._prepare_product_base_line_for_taxes_computation(line)
            self.env['account.tax']._add_tax_details_in_base_line(base_line, move.company_id)
            for tax_data in base_line.get('tax_details', {}).get('taxes_data', []):
                tax = tax_data.get('tax')
                if tax and tax.hka_tax_code == '04' and tax.hka_tax_isc_id:
                    rate_key = round(float(tax.hka_tax_isc_id.rate), 6)
                    per_rate[rate_key] += float(tax_data.get('raw_base_amount_currency') or 0.0)
        return dict(per_rate)

    def _hka_join_descriptions_for_lines(self, move, lines, fallback):
        """U+2028-joined line names for listaItems descripcion (max 500)."""
        move.ensure_one()
        name_chunks = []
        for n in lines.mapped('name'):
            if not n:
                continue
            t = self._hka_normalize_lista_item_descripcion(n, truncate=False)
            if t:
                name_chunks.append(t)
        if name_chunks:
            return '\u2028'.join(name_chunks)[:500]
        return self._hka_normalize_lista_item_descripcion(fallback)

    def _hka_cpbs_fields(self, move, product, uom_code):
        """CPBS fields for government receivers. Requires a mapped product DGI code."""
        move.ensure_one()
        if move.partner_id.dgi_tipo_cliente_fe != '03':
            return {}
        if not product or not product.dgi_code_id or (not product.dgi_code_id.code):
            raise UserError(_('Product DGI/CPBS code is required when the receiver is a government entity (%s).') % (product.display_name if product else _('Unknown product')))
        code = product.dgi_code_id.code
        return {'codigoCPBS': code, 'codigoCPBSAbrev': code[:2], 'unidadMedidaCPBS': uom_code}

    def _hka_prepare_consolidated_invoice_items(self, move, item_lines, tax_parsed):
        """Build listaItems: one row per merged ITBMS tasa / ISC rate (net of all lines).

        Product descriptions are grouped by HKA tax: each row lists only lines sharing
        that ITBMS tasa or the same ISC ``tasaISC`` (rate).

        ``tax_parsed`` is returned by :meth:`_hka_parse_tax_totals_for_hka`.
        """
        move.ensure_one()
        default_ref = item_lines[0]
        names_all_fallback = default_ref.name or default_ref.product_id.name or _('Invoice')
        names_desc_all = self._hka_join_descriptions_for_lines(move, item_lines, names_all_fallback)
        itbms_line_buckets = self._hka_group_item_lines_by_itbms_tasa(move, item_lines)
        isc_line_buckets = self._hka_group_item_lines_by_isc_rate(move, item_lines)
        isc_base_from_lines = self._hka_isc_base_per_rate_from_lines(move, item_lines)

        def base_item_dict(ref_line):
            uom = ref_line.product_uom_id.dgi_code_id.code or 'und'
            it = {'cantidad': '1.00', 'unidadMedida': uom}
            if ref_line.product_id and ref_line.product_id.default_code:
                it['codigo'] = ref_line.product_id.default_code
            it.update(self._hka_cpbs_fields(move, ref_line.product_id, uom))
            return it
        itbms_rows = list(tax_parsed['itbms_rows'])
        isc_rows = list(tax_parsed['isc_rows'])
        total_itbms = tax_parsed['total_itbms']
        total_isc = tax_parsed['total_isc']
        isc_carry_net_only = not itbms_rows and isc_rows and move.currency_id.is_zero(total_itbms) and (not move.currency_id.is_zero(move.amount_untaxed))
        if not itbms_rows and (not move.currency_id.is_zero(move.amount_untaxed)):
            if not isc_carry_net_only:
                b0 = move.currency_id.round(move.amount_untaxed)
                itbms_rows = [('00', b0, 0.0)]
                total_itbms = 0.0
        items = []
        for tasa, base_raw, tax_raw in itbms_rows:
            lines_t = itbms_line_buckets.get(tasa, self.env['account.move.line'])
            ref_line = lines_t[:1] or default_ref
            fallback_lbl = '%s — %s' % (names_all_fallback, _('ITBMS %s') % tasa)
            desc = self._hka_join_descriptions_for_lines(move, lines_t, fallback_lbl).strip()
            if not desc:
                desc = (names_desc_all or _('ITBMS %s') % tasa)[:500]
            it = base_item_dict(ref_line)
            it['descripcion'] = desc[:500]
            b = move.currency_id.round(base_raw)
            tx = move.currency_id.round(tax_raw)
            it['precioUnitario'] = '{:.2f}'.format(b)
            it['precioItem'] = '{:.2f}'.format(b)
            it['tasaITBMS'] = tasa
            it['valorITBMS'] = '{:.2f}'.format(tx)
            it['valorTotal'] = '{:.2f}'.format(move.currency_id.round(b + tx))
            items.append(it)
        for rate_key, base_raw, isc_raw in isc_rows:
            rate_str = str(rate_key)
            lines_r = isc_line_buckets.get(rate_key, self.env['account.move.line'])
            ref_line = lines_r[:1] or default_ref
            isc_lbl = _('ISC %s') % rate_str
            fallback_lbl = '%s — %s' % (names_all_fallback, isc_lbl)
            desc = self._hka_join_descriptions_for_lines(move, lines_r, fallback_lbl).strip()
            if not desc:
                desc = (names_desc_all or isc_lbl)[:500]
            it = base_item_dict(ref_line)
            it['descripcion'] = desc[:500]
            b = move.currency_id.round(base_raw)
            if isc_carry_net_only and move.currency_id.is_zero(b):
                bline = isc_base_from_lines.get(rate_key)
                if bline and (not move.currency_id.is_zero(bline)):
                    b = move.currency_id.round(bline)
            isc_amt = move.currency_id.round(isc_raw)
            it['precioUnitario'] = '{:.2f}'.format(b)
            it['precioItem'] = '{:.2f}'.format(b)
            it['tasaITBMS'] = '00'
            it['valorITBMS'] = '{:.2f}'.format(0.0)
            it['tasaISC'] = rate_str
            it['valorISC'] = '{:.2f}'.format(isc_amt)
            it['valorTotal'] = '{:.2f}'.format(move.currency_id.round(b + isc_amt))
            items.append(it)
        if not items:
            it = base_item_dict(default_ref)
            it['descripcion'] = names_desc_all
            b = move.currency_id.round(move.amount_untaxed)
            t = move.currency_id.round(total_itbms)
            it['precioUnitario'] = it['precioItem'] = '{:.2f}'.format(b)
            it['tasaITBMS'] = '00'
            it['valorITBMS'] = '{:.2f}'.format(t)
            it['valorTotal'] = '{:.2f}'.format(move.currency_id.round(b + t))
            items.append(it)
        sum_b = sum((float(x['precioItem']) for x in items))
        sum_ib = sum((float(x.get('valorITBMS') or 0) for x in items))
        sum_isc = sum((float(x.get('valorISC') or 0) for x in items))
        db = move.currency_id.round(move.amount_untaxed - sum_b)
        dit = move.currency_id.round(total_itbms - sum_ib)
        dis = move.currency_id.round(total_isc - sum_isc)
        if items and (not move.currency_id.is_zero(db) or not move.currency_id.is_zero(dit) or (not move.currency_id.is_zero(dis))):
            _logger.debug('HKA consolidated drift adjustment move=%s db=%s dit=%s dis=%s', move.id, db, dit, dis)
            last = items[-1]
            b = move.currency_id.round(float(last['precioItem']) + db)
            last['precioUnitario'] = last['precioItem'] = '{:.2f}'.format(b)
            if 'valorITBMS' in last:
                vi = move.currency_id.round(float(last['valorITBMS']) + dit)
                last['valorITBMS'] = '{:.2f}'.format(vi)
            if 'valorISC' in last:
                vs = move.currency_id.round(float(last['valorISC']) + dis)
                last['valorISC'] = '{:.2f}'.format(vs)
            last['valorTotal'] = '{:.2f}'.format(move.currency_id.round(float(last['precioItem']) + float(last.get('valorITBMS') or 0) + float(last.get('valorISC') or 0)))
        self._hka_validate_consolidated_items(move, items, tax_parsed)
        return items

    def _check_mapping_codes(self, move):
        """Check if all mapping codes are present - collects all errors before raising"""
        move.ensure_one()
        errors = []
        if not move.invoice_date:
            errors.append(_('Invoice date is required before sending to DGI'))
        if not move.currency_id.dgi_code_id:
            errors.append(_('Currency DGI code is not set for currency %s') % move.currency_id.name)
        if not move.partner_id.country_id.dgi_code_id:
            errors.append(_('Country DGI code is not set for country %s') % move.partner_id.country_id.name)
        if move.move_type in ('out_invoice', 'out_refund'):
            if not move.partner_id.dgi_tipo_cliente_fe:
                errors.append(_('Partner DGI Customer Type is not set for partner %s') % move.partner_id.name)
        if not move.invoice_line_ids:
            errors.append(_('Invoice must have at least one line before sending to DGI'))
        errors.extend(self._dgi_product_line_tax_errors(move))
        for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.product_uom_id):
            if move.partner_id.dgi_tipo_cliente_fe == '03' and (not line.product_id.dgi_code_id):
                errors.append(_("Product DGI/CPBS code is not set for product '%s' (line: %s). Required for government receivers.") % (line.product_id.name or _('Unknown'), line.name or line.id))
            if not line.product_uom_id.dgi_code_id:
                errors.append(_("UOM DGI code is not set for UOM '%s' (line: %s)") % (line.product_uom_id.name or _('Unknown'), line.name or line.id))
        if not move.journal_id.dgi_codigo_sucursal_emisor:
            errors.append(_('Journal Branch Code is not configured for journal %s') % move.journal_id.name)
        if not move.journal_id.dgi_punto_facturacion_fiscal:
            errors.append(_('Journal Fiscal Point is not configured for journal %s') % move.journal_id.name)
        elif move.journal_id.dgi_punto_facturacion_fiscal == '000':
            errors.append(_('Journal Fiscal Point cannot be 000'))
        number = (move.name or '').strip()
        if number and number != '/' and (not (number.isdigit() and len(number) == 10)):
            errors.append(_('Fiscal document number must be exactly 10 digits (0000000001 to 9999999999). Current value: %s') % number)
        pais = ''
        if move.partner_id.country_id and move.partner_id.country_id.dgi_code_id:
            pais = move.partner_id.country_id.dgi_code_id.code or ''
        elif move.partner_id.country_id:
            pais = 'ZZ'
        if move.hka_destino_operacion == '1' and pais and (pais != 'PA'):
            errors.append(_('Destination is Panama but the receiver country code is %s. Set Destination to Foreign or use a Panama partner.') % pais)
        if move.hka_destino_operacion == '2' and pais == 'PA':
            errors.append(_('Destination is Foreign but the receiver country code is PA. Set Destination to Panama or use a foreign partner.'))
        for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            desc = (line.name or line.product_id.name or '').strip()
            if desc and len(desc) < 2:
                errors.append(_('Line description must be at least 2 characters (HKA). Line: %s') % desc)
        if errors:
            error_message = _('Cannot send invoice to DGI. Please fix the following issues:\n- %s') % '\n- '.join(errors)
            raise UserError(error_message)

    @api.model
    def validate_for_send(self, move):
        """Validate invoice before sending to DGI - common validation logic"""
        move.ensure_one()
        combo_errors = move._hka_combination_errors()
        if combo_errors:
            raise UserError('\n'.join(combo_errors))
        if move.move_type == 'out_invoice':
            if move.hka_tipo_documento in ('04', '05', '06', '07'):
                raise UserError(_("Invalid document type for customer invoice: '%s'. Customer invoices must use document types 01, 03, 08, 09, or 10.") % move.hka_tipo_documento)
        if not move.journal_id.use_dgi_electronic_invoicing:
            raise UserError(_('DGI Electronic Invoicing is not enabled for this journal'))
        if move.dgi_sent:
            raise UserError(_('This document has already been sent to DGI'))
        if move.state != 'posted':
            raise UserError(_('Only posted invoices can be sent to DGI'))
        self._check_mapping_codes(move)
        ref_errors = self._dgi_referenced_cufe_errors(move)
        if ref_errors:
            raise UserError('\n'.join(ref_errors))

    def _hka_dgi_code_merge_key(self, move, line):
        """Group key for same-code merge. Unmapped products stay on their own line."""
        move.ensure_one()
        product = line.product_id
        dgi = product.dgi_code_id if product else False
        if not dgi:
            return ('line', line.id)
        isc_rate = None
        for tax in line.tax_ids:
            if tax.hka_tax_code == '04' and tax.hka_tax_isc_id:
                isc_rate = round(float(tax.hka_tax_isc_id.rate), 6)
                break
        uom_id = line.product_uom_id.id if line.product_uom_id else 0
        return ('code', dgi.id, self._hka_itbms_tasa_for_line(move, line), isc_rate, uom_id)

    def _hka_line_tax_amounts(self, move, line):
        """Signed ITBMS/ISC amounts for one product line."""
        move.ensure_one()
        itbms_tasa = None
        itbms = 0.0
        isc_rate = None
        isc = 0.0
        if not line.tax_ids:
            return (itbms_tasa, itbms, isc_rate, isc)
        base_line = move._prepare_product_base_line_for_taxes_computation(line)
        self.env['account.tax']._add_tax_details_in_base_line(base_line, move.company_id)
        for tax_data in base_line.get('tax_details', {}).get('taxes_data', []):
            tax = tax_data.get('tax')
            if not tax or not tax.hka_tax_code:
                continue
            amount = tax_data.get('raw_tax_amount_currency', 0.0)
            if tax.hka_tax_code in ('00', '01', '02', '03'):
                itbms_tasa = tax.hka_tax_code
                itbms += amount
            elif tax.hka_tax_code == '04' and tax.hka_tax_isc_id:
                isc_rate = tax.hka_tax_isc_id.rate
                isc += amount
        return (itbms_tasa, itbms, isc_rate, isc)

    def _hka_prepare_line_item(self, move, line):
        """One HKA listaItems row from a single positive invoice line."""
        move.ensure_one()
        item = {'descripcion': self._hka_normalize_lista_item_descripcion(line.name or line.product_id.name or ''), 'cantidad': '{:.2f}'.format(line.quantity), 'precioUnitario': '{:.2f}'.format(line.price_unit), 'precioItem': '{:.2f}'.format(line.price_subtotal), 'valorTotal': '{:.2f}'.format(line.price_total)}
        if line.discount > 0:
            discount_amount = line.price_unit * (line.discount / 100)
            item['precioUnitarioDescuento'] = '{:.2f}'.format(discount_amount)
        if line.product_id and line.product_id.default_code:
            item['codigo'] = line.product_id.default_code[:20]
        item['unidadMedida'] = line.product_uom_id.dgi_code_id.code
        if getattr(line, 'is_downpayment', False):
            item['unidadMedida'] = 'und'
        item.update(self._hka_cpbs_fields(move, line.product_id, item.get('unidadMedida')))
        if line.tax_ids:
            mapped_hka = False
            base_line = move._prepare_product_base_line_for_taxes_computation(line)
            self.env['account.tax']._add_tax_details_in_base_line(base_line, move.company_id)
            for tax_data in base_line.get('tax_details', {}).get('taxes_data', []):
                tax = tax_data.get('tax')
                if tax and tax.hka_tax_code:
                    mapped_hka = True
                    tax_amount = abs(tax_data.get('raw_tax_amount_currency', 0.0))
                    if tax.hka_tax_code in ('00', '01', '02', '03'):
                        item['tasaITBMS'] = tax.hka_tax_code
                        item['valorITBMS'] = '{:.2f}'.format(tax_amount)
                    elif tax.hka_tax_code == '04':
                        item['tasaISC'] = str(tax.hka_tax_isc_id.rate)
                        item['valorISC'] = '{:.2f}'.format(tax_amount)
            if not mapped_hka:
                raise UserError(
                    _(
                        "Cannot build HKA payload: line '%s' has taxes but none "
                        "have an HKA tax code."
                    )
                    % (line.name or line.product_id.name or line.id)
                )
            if 'tasaITBMS' not in item:
                item['tasaITBMS'] = '00'
        else:
            item['tasaITBMS'] = '00'
        item.setdefault('valorITBMS', '0.00')
        return item

    def _hka_positive_qty_lines_for_merge(self, move, lines):
        """Positive lines that can back a merged e-factura item."""
        move.ensure_one()
        rnd = move.currency_id.rounding or 0.01
        return lines.filtered(lambda line: line.quantity > 0 and float_compare(line.price_subtotal, 0.0, precision_rounding=rnd) >= 0)

    def _hka_prepare_merged_item_from_lines(self, move, lines):
        """Net one HKA item from lines that share a DGI code. None if the net is invalid.

        Merged rows are always quantity 1 with the net total as unit price so
        HKA's ``cantidad * precioUnitario == precioItem`` cannot drift.
        """
        move.ensure_one()
        rnd = move.currency_id.rounding or 0.01
        pos_lines = self._hka_positive_qty_lines_for_merge(move, lines)
        precio_item = move.currency_id.round(sum(lines.mapped('price_subtotal')))
        if not pos_lines or float_compare(precio_item, 0.0, precision_rounding=rnd) < 0:
            return None
        ref = pos_lines[:1] or lines[:1]
        fallback = ref.name or ref.product_id.name or _('Invoice')
        total_str = '{:.2f}'.format(precio_item)
        item = {'descripcion': self._hka_join_descriptions_for_lines(move, lines, fallback), 'cantidad': '1.00', 'precioUnitario': total_str, 'precioItem': total_str, 'valorTotal': total_str}
        codes = {product.default_code for product in lines.mapped('product_id') if product.default_code}
        if len(codes) == 1:
            item['codigo'] = codes.pop()[:20]
        elif ref.product_id and ref.product_id.default_code:
            item['codigo'] = ref.product_id.default_code[:20]
        if any((getattr(line, 'is_downpayment', False) for line in lines)):
            item['unidadMedida'] = 'und'
        else:
            uoms = {line.product_uom_id.dgi_code_id.code for line in pos_lines if line.product_uom_id.dgi_code_id}
            if len(uoms) == 1:
                item['unidadMedida'] = uoms.pop()
            elif ref.product_uom_id.dgi_code_id:
                item['unidadMedida'] = ref.product_uom_id.dgi_code_id.code
            else:
                item['unidadMedida'] = 'und'
        item.update(self._hka_cpbs_fields(move, ref.product_id, item.get('unidadMedida')))
        itbms_tasa = None
        isc_rate = None
        isc = 0.0
        for line in lines:
            line_tasa, _line_itbms, line_isc_rate, line_isc = self._hka_line_tax_amounts(move, line)
            if line_tasa:
                itbms_tasa = line_tasa
            if line_isc_rate is not None:
                isc_rate = line_isc_rate
                isc += line_isc
        item['tasaITBMS'] = itbms_tasa or '00'
        itbms = self._hka_itbms_amount_from_base(move, precio_item, item['tasaITBMS'])
        item['valorITBMS'] = '{:.2f}'.format(itbms)
        if isc_rate is not None:
            item['tasaISC'] = str(isc_rate)
            item['valorISC'] = '{:.2f}'.format(move.currency_id.round(isc))
        self._hka_sync_item_valor_total(move, item)
        return item

    def _hka_prepare_merged_items_by_dgi_code(self, move, product_lines):
        """One listaItems row per DGI code (+ tax). None if a group cannot be sent as-is."""
        move.ensure_one()
        groups = defaultdict(lambda: self.env['account.move.line'])
        for line in product_lines:
            groups[self._hka_dgi_code_merge_key(move, line)] |= line
        items = []
        for _key, lines in sorted(groups.items(), key=lambda kv: min(kv[1].ids)):
            if len(lines) == 1 and (not self._hka_line_requires_consolidated_payload(lines)):
                items.append(self._hka_prepare_line_item(move, lines))
                continue
            item = self._hka_prepare_merged_item_from_lines(move, lines)
            if item is None:
                return None
            items.append(item)
        return items

    def _hka_line_requires_consolidated_payload(self, line):
        """Line cannot be sent as-is to HKA: negative quantity or negative untaxed subtotal."""
        move = line.move_id
        rnd = move.currency_id.rounding or 0.01
        if line.quantity < 0:
            return True
        return float_compare(line.price_subtotal, 0.0, precision_rounding=rnd) < 0

    @api.model
    def prepare(self, move):
        """Prepare document data for HKA API Enviar method"""
        move.ensure_one()
        punto_facturacion = move.journal_id.dgi_punto_facturacion_fiscal
        datos_transaccion = {'tipoEmision': move.hka_tipo_emision, 'tipoDocumento': move.hka_tipo_documento, 'numeroDocumentoFiscal': move.name, 'puntoFacturacionFiscal': punto_facturacion, 'fechaEmision': self._format_dgi_datetime(move.invoice_date), 'naturalezaOperacion': move.hka_naturaleza_operacion, 'tipoOperacion': move.hka_tipo_operacion, 'destinoOperacion': move.hka_destino_operacion, 'formatoCAFE': move.hka_formato_cafe, 'entregaCAFE': move.hka_entrega_cafe, 'envioContenedor': move.hka_envio_contenedor, 'procesoGeneracion': move.hka_proceso_generacion, 'tipoSucursal': move.hka_tipo_sucursal, 'cliente': move.partner_id._prepare_dgi_cliente_data()}
        if move.hka_tipo_emision in HKA_CONTINGENCY_EMISSION:
            datos_transaccion['fechaInicioContingencia'] = self._format_dgi_datetime(move.hka_fecha_inicio_contingencia)
            datos_transaccion['motivoContingencia'] = (move.hka_motivo_contingencia or '').strip()
        if move.move_type == 'out_invoice' and move.hka_tipo_documento in HKA_TIPO_VENTA_DOCUMENTS and move.hka_tipo_venta:
            datos_transaccion['tipoVenta'] = move.hka_tipo_venta
        interes = self._prepare_dgi_informacion_interes(move)
        if interes:
            datos_transaccion['informacionInteres'] = interes
        product_lines = move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        item_lines = product_lines.filtered(lambda l: l.quantity > 0)
        consolidate_lines = product_lines.filtered(lambda l: self._hka_line_requires_consolidated_payload(l))
        if consolidate_lines and (not item_lines):
            raise UserError(_('Cannot send to DGI: invoice has no product line with positive quantity. At least one such line is required when other lines have negative quantity or negative subtotal.'))
        tax_totals_dict = move.tax_totals if isinstance(move.tax_totals, dict) else {}
        tax_parsed = self._hka_parse_tax_totals_for_hka(move, tax_totals_dict)
        total_itbms = tax_parsed['total_itbms']
        total_isc = tax_parsed['total_isc']
        lista_items = []
        merged_items = None
        if move.hka_merge_same_dgi_code:
            merged_items = self._hka_prepare_merged_items_by_dgi_code(move, product_lines)
        if merged_items:
            lista_items = merged_items
            total_itbms = move.currency_id.round(sum((float(item.get('valorITBMS') or 0.0) for item in lista_items)))
            total_isc = move.currency_id.round(sum((float(item.get('valorISC') or 0.0) for item in lista_items)))
        elif consolidate_lines:
            lista_items = self._hka_prepare_consolidated_invoice_items(move, item_lines, tax_parsed)
        else:
            lista_items = [self._hka_prepare_line_item(move, line) for line in item_lines]
            self._hka_reconcile_lista_items_itbms(move, lista_items, product_lines, total_itbms)
        if not lista_items:
            raise UserError(_('Cannot send to DGI: invoice has no product lines for e-factura items.'))
        hka_total = move.currency_id.round(move.amount_untaxed + total_itbms + total_isc)
        totales_sub_totales = {'totalPrecioNeto': '{:.2f}'.format(move.amount_untaxed), 'totalITBMS': '{:.2f}'.format(total_itbms), 'totalMontoGravado': '{:.2f}'.format(total_itbms + total_isc), 'totalFactura': '{:.2f}'.format(hka_total), 'totalValorRecibido': '{:.2f}'.format(hka_total), 'totalTodosItems': '{:.2f}'.format(hka_total), 'tiempoPago': '2' if move.hka_forma_pago == '01' else '1', 'nroItems': str(len(lista_items)), 'listaFormaPago': [{'formaPagoFact': move.hka_forma_pago, 'valorCuotaPagada': '{:.2f}'.format(hka_total), **({'descFormaPago': move.hka_desc_forma_pago.strip()} if move.hka_forma_pago == '99' and move.hka_desc_forma_pago else {})}]}
        if total_isc > 0:
            totales_sub_totales['totalISC'] = '{:.2f}'.format(total_isc)
        if move.hka_destino_operacion == '2' or move.partner_id.dgi_tipo_cliente_fe == '04':
            if not move.invoice_incoterm_id or not move.invoice_incoterm_id.dgi_code_id:
                raise UserError(_('Incoterm DGI code is not set for incoterm %s') % (move.invoice_incoterm_id.name if move.invoice_incoterm_id else ''))
            export_vals = {'condicionesEntrega': move.invoice_incoterm_id.dgi_code_id.code, 'monedaOperExportacion': move.currency_id.dgi_code_id.code}
            if move.currency_id.name != 'USD':
                usd = self.env.ref('base.USD')
                rate = move.currency_id._convert(1.0, usd, move.company_id, move.invoice_date or fields.Date.context_today(move))
                export_vals['tipoDeCambio'] = '{:.4f}'.format(rate)
                export_vals['montoMonedaExtranjera'] = '{:.4f}'.format(rate * move.amount_total)
            datos_transaccion['datosFacturaExportacion'] = export_vals
        lista_docs_fiscal_referenciados = []
        if move.move_type == 'out_refund' and move.reversed_entry_id:
            original_invoice = move.reversed_entry_id
            if not original_invoice.invoice_date:
                raise UserError(_('Cannot prepare credit note: Original invoice %s is missing invoice date') % original_invoice.name)
            doc_referenciado = {'fechaEmisionDocFiscalReferenciado': self._format_dgi_datetime(original_invoice.invoice_date)}
            if original_invoice.dgi_cufe:
                doc_referenciado['cufeFEReferenciada'] = original_invoice.dgi_cufe
            lista_docs_fiscal_referenciados.append(doc_referenciado)
        if lista_docs_fiscal_referenciados:
            datos_transaccion['listaDocsFiscalReferenciados'] = lista_docs_fiscal_referenciados
        documento = {'codigoSucursalEmisor': move.journal_id.dgi_codigo_sucursal_emisor, 'datosTransaccion': datos_transaccion, 'listaItems': lista_items, 'totalesSubTotales': totales_sub_totales}
        return {'documento': documento}

    def _dgi_requires_product_line_taxes(self, move):
        """Customer invoices/refunds on a DGI journal must have a tax on every product line."""
        move.ensure_one()
        return move.journal_id.use_dgi_electronic_invoicing and move.move_type in ('out_invoice', 'out_refund')

    def _dgi_hka_tax_mapping_errors(self, tax):
        """HKA codes must be set and match the Odoo tax rate (00/01/02/03)."""
        if not tax.hka_tax_code:
            return [_("Tax '%s' has no HKA tax code. Map it to 00, 01, 02, 03, or 04 before confirming a DGI invoice.") % tax.display_name]
        if tax.hka_tax_code in HKA_ITBMS_RATES:
            expected = HKA_ITBMS_RATES[tax.hka_tax_code] * 100.0
            if tax.amount_type != 'percent' or float_compare(tax.amount, expected, precision_digits=2):
                return [_("Tax '%(tax)s' is HKA code %(code)s (%(expected)g%%) but its Odoo rate is %(actual)g%%.") % {'tax': tax.display_name, 'code': tax.hka_tax_code, 'expected': expected, 'actual': tax.amount}]
            return []
        if tax.hka_tax_code == '04' and (not tax.hka_tax_isc_id):
            return [_("Tax '%s' is HKA ISC (04) but has no HKA ISC rate.") % tax.display_name]
        return []

    def _dgi_product_line_tax_errors(self, move):
        move.ensure_one()
        errors = []
        for line in move.invoice_line_ids.filtered(lambda line: line.display_type == 'product'):
            if not line.tax_ids:
                errors.append(_("Tax is required on invoice line '%s'. Use a 0%% tax for exempt lines.") % (line.name or line.product_id.name or line.id))
                continue
            for tax in line.tax_ids:
                errors.extend(self._dgi_hka_tax_mapping_errors(tax))
        return errors

    def _dgi_referenced_cufe_errors(self, move):
        """Electronic credit notes (04) must reference a 66-character CUFE."""
        move.ensure_one()
        if move.hka_tipo_documento != '04':
            return []
        origin = move.reversed_entry_id
        if not origin:
            return [
                _(
                    "Document type 04 requires the original e-factura. "
                    "Create this credit note from the posted invoice."
                )
            ]
        cufe = origin.dgi_cufe or ''
        if len(cufe) != 66:
            return [
                _(
                    "Cannot send credit note: referenced CUFE must be 66 characters "
                    "(HKA cufeFEReferenciada). Current length: %s"
                )
                % len(cufe)
            ]
        if not origin.invoice_date:
            return [
                _("Cannot send credit note: Original invoice date is missing for invoice %s")
                % origin.name
            ]
        return []

    def _check_dgi_product_line_taxes(self, move):
        move.ensure_one()
        errors = self._dgi_product_line_tax_errors(move)
        if errors:
            raise UserError('\n'.join(errors))
