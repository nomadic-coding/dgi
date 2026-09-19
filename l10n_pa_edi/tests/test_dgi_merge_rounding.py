# -*- coding: utf-8 -*-

from odoo import Command
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

    def test_merge_penny_remainder_keeps_formula(self):
        invoice, item = self._merged_item([
            {"name": "Line A", "quantity": 1, "price_unit": 10.00},
            {"name": "Line B", "quantity": 1, "price_unit": 10.00},
            {"name": "Line C", "quantity": 1, "price_unit": 10.01},
        ])
        self.assertAlmostEqual(invoice.amount_untaxed, 30.01)
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "30.01")
        self.assertEqual(item["precioItem"], "30.01")
        self._assert_hka_item_formula(item)

    def test_merge_seven_repeating_cents(self):
        _invoice, item = self._merged_item([
            {"name": "Line %s" % index, "quantity": 1, "price_unit": 0.33}
            for index in range(7)
        ])
        self.assertEqual(item["precioItem"], "2.31")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "2.31")
        # HKA taxes the merged net (2.31 * 7% = 0.16), not 7 * round(0.33 * 7%).
        self.assertEqual(item["valorITBMS"], "0.16")
        self._assert_hka_item_formula(item)

    def test_merge_mixed_quantities_uneven_net(self):
        _invoice, item = self._merged_item([
            {"name": "Two units", "quantity": 2, "price_unit": 10.00},
            {"name": "Penny", "quantity": 1, "price_unit": 0.01},
        ])
        self.assertEqual(item["precioItem"], "20.01")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "20.01")
        self._assert_hka_item_formula(item)

    def test_merge_fractional_quantities(self):
        _invoice, item = self._merged_item([
            {"name": "Half A", "quantity": 1.5, "price_unit": 10.00},
            {"name": "Half B", "quantity": 1.5, "price_unit": 10.00},
            {"name": "Penny", "quantity": 0.01, "price_unit": 1.00},
        ])
        self.assertEqual(item["precioItem"], "30.01")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "30.01")
        self._assert_hka_item_formula(item)

    def test_merge_ten_split_across_three_lines(self):
        _invoice, item = self._merged_item([
            {"name": "Line A", "quantity": 1, "price_unit": 3.33},
            {"name": "Line B", "quantity": 1, "price_unit": 3.33},
            {"name": "Line C", "quantity": 1, "price_unit": 3.34},
        ])
        self.assertEqual(item["precioItem"], "10.00")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "10.00")
        self._assert_hka_item_formula(item)

    def test_merge_one_cent_over_three(self):
        _invoice, item = self._merged_item([
            {"name": "Line A", "quantity": 1, "price_unit": 0.03},
            {"name": "Line B", "quantity": 1, "price_unit": 0.03},
            {"name": "Line C", "quantity": 1, "price_unit": 0.04},
        ])
        self.assertEqual(item["precioItem"], "0.10")
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "0.10")
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
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "227.50")
        self.assertEqual(item["precioItem"], "227.50")
        self._assert_hka_payload_matches_move(invoice, payload)
        self._assert_hka_item_formula(item)

    def test_merge_with_same_code_negative_discount_keeps_formula(self):
        invoice = self._create_negative_discount_invoice()
        payload = self._assert_hka_payload_deducts_negative_lines(invoice, 1000.0)
        item = payload["documento"]["listaItems"][0]
        self.assertEqual(len(payload["documento"]["listaItems"]), 1)
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], item["precioItem"])
        self._assert_hka_item_formula(item)

    def test_merge_zero_tax_lines_have_no_itbms(self):
        invoice, item = self._merged_item([
            {
                "name": "Exempt A",
                "quantity": 1,
                "price_unit": 10.00,
                "tax_ids": [Command.set(self.tax_itbms_0.ids)],
            },
            {
                "name": "Exempt B",
                "quantity": 1,
                "price_unit": 10.00,
                "tax_ids": [Command.set(self.tax_itbms_0.ids)],
            },
            {
                "name": "Exempt C",
                "quantity": 1,
                "price_unit": 10.01,
                "tax_ids": [Command.set(self.tax_itbms_0.ids)],
            },
        ])
        self.assertAlmostEqual(invoice.amount_untaxed, 30.01)
        self.assertAlmostEqual(invoice.amount_tax, 0.0)
        self.assertEqual(item["cantidad"], "1.00")
        self.assertEqual(item["precioUnitario"], "30.01")
        self.assertEqual(item["precioItem"], "30.01")
        self.assertEqual(item["tasaITBMS"], "00")
        self.assertEqual(item["valorITBMS"], "0.00")
        self.assertEqual(item["valorTotal"], "30.01")
        self._assert_hka_item_formula(item)
