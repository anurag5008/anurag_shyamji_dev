import frappe


def execute():
	if not frappe.db.table_exists("tabDaily Planning"):
		return
	if not frappe.db.table_exists("tabSeason Master"):
		return
	if not frappe.db.has_column("Daily Planning", "season_name"):
		return

	has_legacy_season = frappe.db.has_column("Daily Planning", "season")
	has_legacy_year = frappe.db.has_column("Daily Planning", "season_year")

	select_fields = ["name", "season_name"]
	if has_legacy_season:
		select_fields.append("season")
	if has_legacy_year:
		select_fields.append("season_year")

	for row in frappe.db.sql(
		f"""
		SELECT {", ".join(select_fields)}
		FROM `tabDaily Planning`
		WHERE (season_name IS NULL OR season_name = '')
		""",
		as_dict=True,
	):
		if row.season_name:
			continue

		crop = (row.get("season") or "").strip() if has_legacy_season else ""
		year = (row.get("season_year") or "").strip() if has_legacy_year else ""
		if not crop or not year:
			continue

		season_link = f"{crop} {year}"
		if not frappe.db.exists("Season Master", season_link):
			frappe.get_doc(
				{
					"doctype": "Season Master",
					"crop_season": crop,
					"year": year,
				}
			).insert(ignore_permissions=True)

		frappe.db.set_value(
			"Daily Planning", row.name, "season_name", season_link, update_modified=False
		)
