import frappe

from ivri_od.procurement.doctype.season_master.season_master import get_or_create_season_master


def execute():
	if not frappe.db.table_exists("tabSeason Mapping"):
		return
	if not frappe.db.table_exists("tabSeason Master"):
		return

	for row in frappe.db.sql(
		"""
		SELECT name, season, season_year
		FROM `tabSeason Mapping`
		WHERE season IS NOT NULL AND season != ''
		""",
		as_dict=True,
	):
		season = (row.season or "").strip()
		if frappe.db.exists("Season Master", season):
			continue

		crop = season
		year = (row.season_year or "").strip()
		if crop not in ("Kharif", "Rabi") or not year:
			continue

		season_link = get_or_create_season_master(crop, year)
		if not season_link:
			continue

		frappe.db.set_value(
			"Season Mapping",
			row.name,
			{"season": season_link, "season_year": year},
			update_modified=False,
		)
