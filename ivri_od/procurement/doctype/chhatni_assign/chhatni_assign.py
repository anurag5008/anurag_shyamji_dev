# Copyright (c) 2026, Profezzo and contributors

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class ChhatniAssign(Document):
	def validate(self):
		kg = flt(self.chutney_quantity_kg_per_quintal)
		self.chutney_quantity_kg_per_quintal = kg
		# 1 quintal = 100 kg → kg per quintal equals percentage of total weight
		self.chutney_percentage = kg

	def before_save(self):
		self._record_chhatni_change_history()

	def on_update(self):
		sync_target_allocations_from_chhatni_assign(self)

	def after_insert(self):
		sync_target_allocations_from_chhatni_assign(self)

	def _record_chhatni_change_history(self):
		new_kg = flt(self.chutney_quantity_kg_per_quintal)
		if self.is_new():
			self._append_chhatni_history_row(
				old_kg=0,
				new_kg=new_kg,
				note=_("Initial chhatni recorded"),
			)
			return

		old_kg = flt(
			frappe.db.get_value(
				self.doctype,
				self.name,
				"chutney_quantity_kg_per_quintal",
			)
		)
		if old_kg == new_kg:
			return

		self._append_chhatni_history_row(
			old_kg=old_kg,
			new_kg=new_kg,
			note=_("Chhatni updated from {0} to {1} kg per quintal").format(old_kg, new_kg),
		)

	def _append_chhatni_history_row(self, old_kg, new_kg, note=""):
		self.append(
			"chhatni_history",
			{
				"change_datetime": now_datetime(),
				"changed_by": frappe.session.user,
				"old_chhatni_kg": flt(old_kg),
				"new_chhatni_kg": flt(new_kg),
				"change_note": note,
			},
		)


def sync_target_allocations_from_chhatni_assign(chhatni_assign):
	"""Push Chhatni Assign values into Target Allocation (same Season + PPC + Mill)."""
	season = (chhatni_assign.season or "").strip()
	ppc_name = (chhatni_assign.ppc_name or "").strip()
	mill_name = (chhatni_assign.mill_name or "").strip()
	if not (season and ppc_name and mill_name):
		return

	chhatni_val = flt(chhatni_assign.chutney_quantity_kg_per_quintal)
	chhatni_pct = flt(chhatni_assign.chutney_percentage)

	values = {
		"chhatni": chhatni_val,
		"latest_chutney_assign": chhatni_assign.name,
		"latest_chutney_season": season,
		"latest_chutney_kg_per_quintal": chhatni_val,
		"latest_chutney_percentage": chhatni_pct,
	}

	target_names = frappe.get_all(
		"Target Allocation",
		filters={"season": season, "ppc_name": ppc_name, "mill_name": mill_name},
		pluck="name",
	)
	if not target_names:
		return

	from ivri_od.procurement.doctype.target_allocation.target_allocation import (
		sync_season_mappings_from_allocation,
	)

	for name in target_names:
		frappe.db.set_value("Target Allocation", name, values, update_modified=True)
		sync_season_mappings_from_allocation(season, ppc_name, mill_name)
