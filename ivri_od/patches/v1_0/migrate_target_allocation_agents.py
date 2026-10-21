"""Migrate existing Target Allocation agent_name into Target Allocation Agent child table."""

import frappe
from frappe.utils import now


def execute():
	frappe.reload_doc("Procurement", "doctype", "target_allocation_agent")
	frappe.reload_doc("Procurement", "doctype", "target_allocation")

	if not frappe.db.table_exists("Target Allocation Agent"):
		return

	allocations = frappe.db.sql(
		"""
		SELECT name, agent_name
		FROM `tabTarget Allocation`
		WHERE IFNULL(agent_name, '') != ''
		""",
		as_dict=True,
	)

	now_time = now()
	for alloc in allocations:
		exists = frappe.db.sql(
			"""
			SELECT name FROM `tabTarget Allocation Agent`
			WHERE parent = %s AND parentfield = 'agent_details'
			LIMIT 1
			""",
			(alloc.name,),
		)
		if not exists:
			child_name = frappe.generate_hash(length=10)
			frappe.db.sql(
				"""
				INSERT INTO `tabTarget Allocation Agent`
				(name, creation, modified, modified_by, owner, parent, parenttype, parentfield, idx, agent_name)
				VALUES (%s, %s, %s, 'Administrator', 'Administrator', %s, 'Target Allocation', 'agent_details', 1, %s)
				""",
				(child_name, now_time, now_time, alloc.name, alloc.agent_name.strip()),
			)

	frappe.db.commit()
	frappe.clear_cache(doctype="Target Allocation")
	frappe.clear_cache(doctype="Target Allocation Agent")
