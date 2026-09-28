# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

class TestWeighBridgeMeasurement(FrappeTestCase):
	def test_gunny_cut_requires_jute_weight_when_jute_bags_present(self):
		doc = frappe.get_doc(
			{
				"doctype": "Weigh Bridge Measurement",
				"gunny_type": "Gunny Cut",
				"gunny_weight": 0,
				"bag_weight_details": [
					{
						"jute_bags": 10,
						"plastic_bags": 0,
						"weight_per_jute_kg": 0,
						"weight_per_plastic_kg": 0,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc._validate_bag_detail_weights()

	def test_gunny_cut_requires_plastic_weight_when_plastic_bags_present(self):
		doc = frappe.get_doc(
			{
				"doctype": "Weigh Bridge Measurement",
				"gunny_type": "Gunny Cut",
				"gunny_weight": 0,
				"bag_weight_details": [
					{
						"jute_bags": 0,
						"plastic_bags": 5,
						"weight_per_jute_kg": 0,
						"weight_per_plastic_kg": 0,
					}
				],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc._validate_bag_detail_weights()

	def test_gunny_cut_passes_when_weights_filled(self):
		doc = frappe.get_doc(
			{
				"doctype": "Weigh Bridge Measurement",
				"gunny_type": "Gunny Cut",
				"gunny_weight": 1.5,
				"bag_weight_details": [
					{
						"jute_bags": 10,
						"plastic_bags": 0,
						"weight_per_jute_kg": 1.5,
						"weight_per_plastic_kg": 0,
					}
				],
			}
		)
		doc._validate_bag_detail_weights()
