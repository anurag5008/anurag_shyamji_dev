# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from ivri_od.procurement.doctype.daily_planning.daily_planning import (
	_compact_upper,
	_ppc_transit_match_values,
)


class TestDailyPlanning(FrappeTestCase):
	def test_compact_ppc_matches_excel_and_master_title(self):
		excel_ppc = "GAMBHARI(S1050406)"
		master_title = "GAMBHARI (S1050406)"
		self.assertEqual(_compact_upper(excel_ppc), _compact_upper(master_title))

	def test_ppc_transit_match_values_include_compact_title(self):
		ppc = frappe.get_doc(
			{
				"doctype": "PPC Master",
				"code": "S1050406",
				"ppc_name": "GAMBHARI",
			}
		).insert(ignore_permissions=True)

		values = _ppc_transit_match_values(ppc.name)
		self.assertIn(_compact_upper("GAMBHARI(S1050406)"), values)
