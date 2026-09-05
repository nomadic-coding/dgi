# -*- coding: utf-8 -*-

from odoo.tests import tagged

from .common import L10nPaEdiTestCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestL10nPaEdiMergeRounding(L10nPaEdiTestCommon):
    """HKA identity: precioItem = cantidad * (precioUnitario - descuento)."""

    def _merged_item(self, line_vals):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[
                {**self._default_invoice_line_vals(), **vals} for vals in line_vals
            ],
        )
        payload = invoice._prepare_dgi_document_data()
        items = payload["documento"]["listaItems"]
        self.assertEqual(len(items), 1, payload)
        self._assert_hka_payload_matches_move(invoice, payload)
        return invoice, items[0]

    def test_helper_even_division_uses_two_decimals(self):
        invoice = self._create_dgi_invoice(post=False)
        self.assertEqual(invoice._hka_format_merged_unit_price(100.00, 2), "50.00")

    def test_helper_thirty_cent_split_uses_extra_decimals(self):
        invoice = self._create_dgi_invoice(post=False)
        unit = invoice._hka_format_merged_unit_price(30.01, 3)
        self.assertTrue(unit)
        self.assertAlmostEqual(3 * float(unit), 30.01, places=2)

    def test_helper_ten_over_three(self):
        invoice = self._create_dgi_invoice(post=False)
        unit = invoice._hka_format_merged_unit_price(10.00, 3)
        self.assertEqual(unit, "3.333")
        self.assertAlmostEqual(3 * float(unit), 10.00, places=2)

    def test_helper_zero_qty_has_no_unit_price(self):
        invoice = self._create_dgi_invoice(post=False)
        self.assertIsNone(invoice._hka_format_merged_unit_price(10.00, 0))

    def test_merge_penny_remainder_keeps_formula(self):
        invoice, item = self._merged_item([
            {"name": "Line A", "quantity": 1, "price_unit": 10.00},
            {"name": "Line B", "quantity": 1, "price_unit": 10.00},
            {"name": "Line C", "quantity": 1, "price_unit": 10.01},
        ])
        self.assertAlmostEqual(invoice.amount_untaxed, 30.01)
        self.assertEqual(item["precioItem"], "30.01")
        self._assert_hka_item_formula(item)

    def test_merge_seven_repeating_cents(self):
        _invoice, item = self._merged_item([
            {"name": "Line %s" % index, "quantity": 1, "price_unit": 0.33}
            for index in range(7)
        ])
        self.assertEqual(item["precioItem"], "2.31")
        self.assertEqual(item["cantidad"], "7.00")
        # HKA taxes the merged net (2.31 * 7% = 0.16), not 7 * round(0.33 * 7%).
        self.assertEqual(item["valorITBMS"], "0.16")
        self._assert_hka_item_formula(item)

    def test_merge_mixed_quantities_uneven_net(self):
        _invoice, item = self._merged_item([
            {"name": "Two units", "quantity": 2, "price_unit": 10.00},
            {"name": "Penny", "quantity": 1, "price_unit": 0.01},
        ])
        self.assertEqual(item["precioItem"], "20.01")
        self.assertEqual(item["cantidad"], "3.00")
        self._assert_hka_item_formula(item)

    def test_merge_fractional_quantities(self):
        _invoice, item = self._merged_item([
            {"name": "Half A", "quantity": 1.5, "price_unit": 10.00},
            {"name": "Half B", "quantity": 1.5, "price_unit": 10.00},
            {"name": "Penny", "quantity": 0.01, "price_unit": 1.00},
        ])
        self.assertEqual(item["precioItem"], "30.01")
        self._assert_hka_item_formula(item)

    def test_merge_ten_split_across_three_lines(self):
        _invoice, item = self._merged_item([
            {"name": "Line A", "quantity": 1, "price_unit": 3.33},
            {"name": "Line B", "quantity": 1, "price_unit": 3.33},
            {"name": "Line C", "quantity": 1, "price_unit": 3.34},
        ])
        self.assertEqual(item["precioItem"], "10.00")
        self.assertEqual(item["cantidad"], "3.00")
        self._assert_hka_item_formula(item)

    def test_merge_one_cent_over_three(self):
        _invoice, item = self._merged_item([
            {"name": "Line A", "quantity": 1, "price_unit": 0.03},
            {"name": "Line B", "quantity": 1, "price_unit": 0.03},
            {"name": "Line C", "quantity": 1, "price_unit": 0.04},
        ])
        self.assertEqual(item["precioItem"], "0.10")
        self._assert_hka_item_formula(item)

    def test_merge_discount_percent_lines_keep_formula(self):
        invoice = self._create_dgi_invoice(
            partner=self.partner_contribuyente,
            line_vals=[
                {
                    **self._default_invoice_line_vals(),
                    "name": "Discounted A",
                    "quantity": 2,
                    "price_unit": 100.0,
                    "discount": 10.0,
                },
                {
                    **self._default_invoice_line_vals(),
                    "name": "Discounted B",
                    "quantity": 1,
                    "price_unit": 50.0,
                    "discount": 5.0,
                },
            ],
        )
        payload = invoice._prepare_dgi_document_data()
        item = payload["documento"]["listaItems"][0]
        self.assertEqual(len(payload["documento"]["listaItems"]), 1)
        self.assertAlmostEqual(invoice.amount_untaxed, 227.50)
        self._assert_hka_payload_matches_move(invoice, payload)
        self._assert_hka_item_formula(item)

    def test_merge_with_same_code_negative_discount_keeps_formula(self):
        invoice = self._create_negative_discount_invoice()
        payload = self._assert_hka_payload_deducts_negative_lines(invoice, 1000.0)
        self.assertEqual(len(payload["documento"]["listaItems"]), 1)
        self._assert_hka_item_formula(payload["documento"]["listaItems"][0])
