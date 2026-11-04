# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Net Weight of a DCRO DC Transit Challan row whose AC Note is not available (no
file, a scanned image, or no "Net Weight" on it). See portal_sync.add_ac_note_net_weight."""

from frappe.model.document import Document


class IfFCIACNotAvailable(Document):
	pass
