# Copyright (c) 2026, Profezzo and contributors

from frappe.model.document import Document


class AgentMaster(Document):
	def validate(self):
		if self.agent_name:
			self.agent_name = self.agent_name.strip()
