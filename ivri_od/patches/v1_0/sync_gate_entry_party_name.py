# Copyright (c) 2026, Profezzo and contributors

import frappe

from ivri_od.procurement.doctype.gate_entry.gate_entry import GATE_ENTRY_PARTY_NAME_FIELDS


def execute():
	if not frappe.db.has_column("Gate Entry", "party_name"):
		return
	if not frappe.db.has_column("Gate Entry", "custom_party_name"):
		return

	rows = frappe.db.sql(
		"""
		select name, party_name, custom_party_name
		from `tabGate Entry`
		where
			(party_name is null or party_name = '')
			and custom_party_name is not null
			and custom_party_name != ''
		""",
		as_dict=True,
	)
	for row in rows:
		party = (row.custom_party_name or "").strip()
		if not party:
			continue
		frappe.db.set_value("Gate Entry", row.name, "party_name", party, update_modified=False)
