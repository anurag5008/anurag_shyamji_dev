"""Show TP No (Transit Pass No) as a Weigh Bridge Measurement list column.

A list setting saved from the desk (Property Setter) had switched this column off, and it wins over the
DocType file. Set it the same way the desk's "Pick Columns" does.
"""

import frappe
from frappe.desk.doctype.list_view_settings.list_view_settings import set_in_list_view_property

DOCTYPE = "Weigh Bridge Measurement"


def execute():
	frappe.reload_doc("procurement", "doctype", "weigh_bridge_measurement")
	set_in_list_view_property(DOCTYPE, frappe.get_meta(DOCTYPE).get_field("transit_pass_no"), "1")
	frappe.clear_cache(doctype=DOCTYPE)
