# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt


class TestTargetAllocation(FrappeTestCase):
	"""
	Integration tests for TargetAllocation multiple agent feature.
	"""

	def test_multiple_agents_on_target_allocation(self):
		test_season = "Rabi 2025"
		test_mill = "M050421"
		test_ppc = "S1050215"

		# Ensure clean state
		existing = frappe.db.get_value(
			"Target Allocation",
			{"season": test_season, "ppc_name": test_ppc, "mill_name": test_mill},
			"name",
		)
		if existing:
			frappe.delete_doc("Target Allocation", existing, force=True)

		# 1. Create with multiple agents
		doc = frappe.new_doc("Target Allocation")
		doc.season = test_season
		doc.ppc_name = test_ppc
		doc.mill_name = test_mill
		doc.target_quantity = 2500.0
		doc.chhatni = 4.0
		doc.append("agent_details", {"agent_name": "Arjun"})
		doc.append("agent_details", {"agent_name": "Aman"})
		doc.append("agent_details", {"agent_name": "Direct"})
		doc.insert(ignore_permissions=True)

		# 2. Reload and verify
		reloaded = frappe.get_doc("Target Allocation", doc.name)
		agents = [row.agent_name for row in reloaded.agent_details]
		self.assertEqual(agents, ["Arjun", "Aman", "Direct"])
		self.assertEqual(reloaded.agent_name, "Arjun")
		self.assertEqual(flt(reloaded.target_quantity), 2500.0)
		self.assertEqual(flt(reloaded.chhatni), 4.0)

		# 3. Edit agents: remove Aman, leaving Arjun and Direct
		reloaded.agent_details = [r for r in reloaded.agent_details if r.agent_name != "Aman"]
		reloaded.save(ignore_permissions=True)

		reloaded2 = frappe.get_doc("Target Allocation", doc.name)
		agents2 = [row.agent_name for row in reloaded2.agent_details]
		self.assertEqual(agents2, ["Arjun", "Direct"])

		# 4. Duplicate agent rejection
		reloaded2.append("agent_details", {"agent_name": "Direct"})
		self.assertRaises(frappe.ValidationError, reloaded2.save)
		frappe.db.rollback()

		# Clean up
		frappe.delete_doc("Target Allocation", doc.name, force=True, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Target Allocation", doc.name))
		self.assertFalse(frappe.db.exists("Target Allocation Agent", {"parent": doc.name}))

	def test_backward_compatibility_single_agent(self):
		test_season = "Rabi 2025"
		test_mill = "M050421"
		test_ppc = "S1050215"

		existing = frappe.db.get_value(
			"Target Allocation",
			{"season": test_season, "ppc_name": test_ppc, "mill_name": test_mill},
			"name",
		)
		if existing:
			frappe.delete_doc("Target Allocation", existing, force=True)

		doc = frappe.new_doc("Target Allocation")
		doc.season = test_season
		doc.ppc_name = test_ppc
		doc.mill_name = test_mill
		doc.target_quantity = 1500.0
		doc.agent_name = "Direct"
		doc.insert(ignore_permissions=True)

		reloaded = frappe.get_doc("Target Allocation", doc.name)
		self.assertEqual(len(reloaded.agent_details), 1)
		self.assertEqual(reloaded.agent_details[0].agent_name, "Direct")
		self.assertEqual(reloaded.agent_name, "Direct")

		frappe.delete_doc("Target Allocation", doc.name, force=True, ignore_permissions=True)
