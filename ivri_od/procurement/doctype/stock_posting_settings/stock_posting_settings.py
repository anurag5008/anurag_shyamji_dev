# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class StockPostingSettings(Document):
	def validate(self):
		"""Item roles stay distinct. Only checks Items that are chosen; creates nothing."""
		roles = {
			_("Government Paddy Item"): self.government_paddy_item,
			_("Raw Rice Item"): self.raw_rice_item,
			_("Boiled Rice Item"): self.boiled_rice_item,
		}
		chosen = [item for item in roles.values() if item]
		if len(set(chosen)) != len(chosen):
			frappe.throw(_("Paddy, Raw Rice and Boiled Rice must be three different Items."))

		by_products = [(row.item_code or "").strip() for row in self.by_product_items]
		if len(set(by_products)) != len(by_products):
			frappe.throw(_("A by-product Item is listed twice."))
		clash = set(by_products) & set(chosen)
		if clash:
			frappe.throw(_("{0} cannot be both a by-product and a paddy or rice Item.").format(", ".join(sorted(clash))))

		for label, item in list(roles.items()) + [(_("By-Product Item"), item) for item in by_products]:
			if item:
				self._validate_item(label, item)

	def _validate_item(self, label, item_code):
		item = frappe.db.get_value(
			"Item", item_code, ["disabled", "is_stock_item", "has_batch_no", "stock_uom"], as_dict=True
		)
		if not item:
			frappe.throw(_("{0}: Item {1} not found.").format(label, item_code))
		if item.disabled or not item.is_stock_item:
			frappe.throw(_("{0}: {1} must be an enabled stock Item, tracked on its own.").format(label, item_code))
		if not item.has_batch_no:
			frappe.throw(
				_("{0}: {1} must have batches enabled so the procurement season stays with the stock.").format(
					label, item_code
				)
			)
