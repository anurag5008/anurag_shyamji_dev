import frappe

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import make_pass_unique_key


def execute():
	if not frappe.db.table_exists("tabPPAS Transit Pass"):
		return
	if not frappe.db.has_column("PPAS Transit Pass", "pass_unique_key"):
		return

	for row in frappe.db.sql(
		"""
		SELECT name, transit_pass_no, ppc, miller, season, pass_unique_key
		FROM `tabPPAS Transit Pass`
		""",
		as_dict=True,
	):
		key = make_pass_unique_key(
			row.transit_pass_no, row.ppc, row.miller, row.season
		)
		if row.pass_unique_key == key:
			continue
		frappe.db.set_value(
			"PPAS Transit Pass",
			row.name,
			"pass_unique_key",
			key,
			update_modified=False,
		)
