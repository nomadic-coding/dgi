# -*- coding: utf-8 -*-

from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiMixTaxes(L10nPaEdiTestCommon):
    """Same DGI code may merge only when the HKA tax code (and ISC rate) match."""

    def _items_by_tasa(self, invoice):
        payload = invoice._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        self._assert_hka_payload_matches_move(invoice, payload)
        return payload, {item["tasaITBMS"]: item for item in items}

    def test_seven_and_ten_percent_same_code_are_not_merged(self):
        invoice = self._create_dgi_invoice(
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Consulting 7%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Consulting 10%"
                ),
            ],
        )
        self.assertAlmostEqual(invoice.amount_untaxed, 2000.0)
        self.assertAlmostEqual(invoice.amount_tax, 170.0)
        self.assertAlmostEqual(invoice.amount_total, 2170.0)
        payload, by_tasa = self._items_by_tasa(invoice)
        self.assertEqual(len(payload["documento"]["listaItems"]), 2)
        self.assertEqual(set(by_tasa), {"01", "02"})
        self.assertEqual(by_tasa["01"]["valorITBMS"], "70.00")
        self.assertEqual(by_tasa["01"]["valorTotal"], "1070.00")
        self.assertEqual(by_tasa["02"]["valorITBMS"], "100.00")
        self.assertEqual(by_tasa["02"]["valorTotal"], "1100.00")
        self._assert_documento_xml_equal(invoice, "invoice_mixed_taxes.xml")

    def test_seven_and_fifteen_percent_same_code_are_not_merged(self):
        invoice = self._create_dgi_invoice(
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Consulting 7%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_15, name="Consulting 15%"
                ),
            ],
        )
        payload, by_tasa = self._items_by_tasa(invoice)
        self.assertEqual(len(payload["documento"]["listaItems"]), 2)
        self.assertEqual(set(by_tasa), {"01", "03"})
        self.assertEqual(by_tasa["01"]["valorITBMS"], "70.00")
        self.assertEqual(by_tasa["03"]["valorITBMS"], "150.00")
        self.assertEqual(payload["documento"]["totalesSubTotales"]["totalITBMS"], "220.00")
        self.assertEqual(payload["documento"]["totalesSubTotales"]["totalFactura"], "2220.00")

    def test_zero_seven_and_ten_percent_stay_three_items(self):
        invoice = self._create_dgi_invoice(
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_0, name="Consulting 0%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Consulting 7%"
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Consulting 10%"
                ),
            ],
        )
        payload, by_tasa = self._items_by_tasa(invoice)
        self.assertEqual(len(payload["documento"]["listaItems"]), 3)
        self.assertEqual(set(by_tasa), {"00", "01", "02"})
        self.assertEqual(by_tasa["00"]["valorITBMS"], "0.00")
        self.assertEqual(by_tasa["01"]["valorITBMS"], "70.00")
        self.assertEqual(by_tasa["02"]["valorITBMS"], "100.00")
        self.assertAlmostEqual(invoice.amount_untaxed, 3000.0)
        self.assertAlmostEqual(invoice.amount_tax, 170.0)

    def test_same_tax_lines_still_merge_beside_a_different_tax(self):
        invoice = self._create_dgi_invoice(
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Seven A", quantity=1, price_unit=1000.0
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_7, name="Seven B", quantity=1, price_unit=1000.0
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Ten", quantity=1, price_unit=1000.0
                ),
            ],
        )
        payload, by_tasa = self._items_by_tasa(invoice)
        self.assertEqual(len(payload["documento"]["listaItems"]), 2)
        self.assertEqual(by_tasa["01"]["cantidad"], "1.00")
        self.assertEqual(by_tasa["01"]["precioUnitario"], "2000.00")
        self.assertEqual(by_tasa["01"]["precioItem"], "2000.00")
        self.assertEqual(by_tasa["01"]["valorITBMS"], "140.00")
        self.assertEqual(by_tasa["02"]["cantidad"], "1.00")
        self.assertEqual(by_tasa["02"]["precioUnitario"], "1000.00")
        self.assertEqual(by_tasa["02"]["valorITBMS"], "100.00")
        self.assertAlmostEqual(invoice.amount_untaxed, 3000.0)
        self.assertAlmostEqual(invoice.amount_tax, 240.0)

    def test_same_ten_percent_lines_are_merged(self):
        invoice = self._create_dgi_invoice(
            line_vals=[
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Ten A", quantity=2, price_unit=100.0
                ),
                self._invoice_line_vals_for_tax(
                    self.tax_itbms_10, name="Ten B", quantity=3, price_unit=100.0
                ),
            ],
        )
        payload, by_tasa = self._items_by_tasa(invoice)
        self.assertEqual(len(payload["documento"]["listaItems"]), 1)
        self.assertEqual(by_tasa["02"]["cantidad"], "1.00")
        self.assertEqual(by_tasa["02"]["precioUnitario"], "500.00")
        self.assertEqual(by_tasa["02"]["valorITBMS"], "50.00")
        self.assertEqual(by_tasa["02"]["valorTotal"], "550.00")
