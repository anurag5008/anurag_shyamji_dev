# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Manual entry of portal rows (button "Manual Entry" on the RRC Detail from SCMS,
DCRO Details and WINGS Details pages).

Used when a row cannot be read from the portal yet. The user pastes rows from
Excel into a grid with the portal's columns; they are saved as Portal Record
with "Entered From" = Manual, so they show in the same SCMS reports.

Portal data has priority:
- a manual row is never saved over a row read from the portal (same key);
- a later portal read replaces the manual row (see portal_sync._upsert_row).
Detail rows (the lots of a DC, the Delivered lines of a TEC) are entered against
their parent row; detail rows read from the portal are never replaced by hand.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from ivri_od.procurement.portal_sync import (
	_set_details,
	build_details_hash,
	build_record_key,
	build_row_hash,
	build_summary,
	fix_section_cells,
	mill_label_keys,
	normalize_cells,
	normalize_details,
	parse_filter_columns,
	parse_key_columns,
	resolve_record_name,
	row_mill_id,
)

SITE = "SCMS"
MAX_MANUAL_ROWS = 500
TOTAL_CELL = re.compile(r"^(grand |sub ?)?total\s*:?$", re.IGNORECASE)

DC_SECTION = "DC Monitoring"

# Columns as on the SCMS pages, in portal order, so rows copied from the
# portal's Excel export paste straight in. Update here if the portal changes.
DC_COLUMNS = [
	"Sl#",
	"DC NO.",
	"Paddy Procurement District",
	"Miller Code",
	"Miller Name",
	"DC Qty(In Qtl.)",
	"Receipt Qty(In Qtl.)",
	"No. Of Lot",
	"Balance Qty(In Qtl.)",
	"Current Status",
]
DC_LOT_COLUMNS = [
	"Sl#",
	"Date Of Receipt",
	"Miller Code",
	"Miller Name",
	"Lot No.",
	"Acceptance Note No.",
	"Bags",
	"Quantity (In Qtl.)",
	"If Receive Against BRL Stock",
	"BRL Lot Details - Lot No.",
	"BRL Lot Details - No Of Bag",
	"BRL Lot Details - Qty(In Qtl)",
]
TRANSIT_COLUMNS = [
	"Sl#",
	"District Name",
	"KMS",
	"Miller Code",
	"Challan No.",
	"Challan Date",
	"DC No",
	"Depot Code",
	"Lot No",
	"Bag",
	"Vehicle No",
	"Driver Name",
	"Commodity",
	"Commodity Category",
	"Lot Challan Receipt status",
]
# "Group - Sub - Letter": the portal's three header rows.
GUNNY_COLUMNS = [
	"Date - A",
	"OB OF GUNNY (in Bags) - B",
	"RECEIPT OF GUNNY (in Bags) - ROAD - C",
	"RECEIPT OF GUNNY (in Bags) - RAKE - D",
	"RECEIPT OF GUNNY (in Bags) - CONCOR - E",
	"RECEIPT OF GUNNY (in Bags) - TRANSFER (RECEIPT INTRA DIST) - F",
	"RECEIPT OF GUNNY (in Bags) - TRANSFER (RECEIPT INTER DIST) - G",
	"RECEIPT OF GUNNY (in Bags) - THROUGH STOCK TRANSFERD - H",
	"RECEIPT OF GUNNY (in Bags) - STOCK TRANSFERD AFTER FCI VERIFICATION - I",
	"RECEIPT OF GUNNY (in Bags) - SPECIAL CASE STOCK TRANSFERD - J",
	"TOTAL RECEIPT (in Bags) - K=(C+D+E+F+G+H+I+J)",
	"TOTAL (in Bags) - L=(K+B)",
	"UTILIZATION (Issue) (in Bags) - OSCSC - M",
	"UTILIZATION (Issue) (in Bags) - FCI - N",
	"UTILIZATION (Issue) (in Bags) - MISC - O",
	"UTILIZATION (Issue) (in Bags) - TRANSFER ISSUE (INTRA DIST) - P",
	"UTILIZATION (Issue) (in Bags) - TRANSFER ISSUE (INTER DIST) - Q",
	"UTILIZATION (Issue) (in Bags) - THROUGH STOCK TRANSFERD - R",
	"UTILIZATION (Issue) (in Bags) - STOCK TRANSFERD AFTER FCI VERIFICATION - S",
	"UTILIZATION (Issue) (in Bags) - SPECIAL CASE STOCK TRANSFER - T",
	"UTILIZATION (Issue) (in Bags) - TOTAL UTILIZATION - U=(M+N+O+P+Q+R+S+T)",
	"BRL DECLARED/DAMAGED AT THE TIME OF DELIVERY (in Bags) - V",
	"BRL DECLARED DURING STORAGE (in Bags) - W",
	"DAMAGED GUNNY DECLARED at FCI (in Bags) - X",
	"FCI DAMAGED & SHORTAGE GUNNY (in Bags) - Y",
	"CLOSING BALANCE (in Bags) - Z=(L-U)-(V+W+X+Y)",
]

# Entries of the "Manual Entry" drop-downs, in menu order. "group" is the page
# whose button lists the form (rrc: RRC Detail from SCMS, dcro: DCRO Details,
# wings: WINGS Details); "site" defaults to SCMS. Without "columns" the grid takes
# the columns of the section's latest row read from the portal (DCRO and WINGS
# pages: columns not known in advance). "lots": the form enters the detail rows
# of one parent row, picked by "parent_label"; "parent_form" adds parent rows.
MANUAL_FORMS = {
	"dc_summary": {"group": "rrc", "label": "RRC DC Summary", "section": DC_SECTION, "columns": DC_COLUMNS},
	"dc_lots": {
		"group": "rrc",
		"label": "RRC DC Summary: Lots of a DC",
		"section": DC_SECTION,
		"columns": DC_LOT_COLUMNS,
		"lots": True,
		"parent_label": "DC NO.",
		"parent_form": "dc_summary",
	},
	"transit_pass": {
		"group": "rrc",
		"label": "RRC Transit Pass",
		"section": "Transit Challan RRC",
		"columns": TRANSIT_COLUMNS,
	},
	"gunny_stock": {
		"group": "rrc",
		"label": "Gunny Stock Register Details",
		"section": "Gunny Stock Register Details",
		"columns": GUNNY_COLUMNS,
	},
	"paddy_release": {"group": "dcro", "label": "Paddy Release", "section": "Paddy Release", "site": "DCRO"},
	"view_dc": {"group": "dcro", "label": "View DC", "section": "View DC", "site": "DCRO"},
	"tec_report": {"group": "wings", "label": "TEC Report", "section": "TEC Report", "site": "WINGS"},
	"tec_delivered": {
		"group": "wings",
		"label": "TEC Report: Delivered lines of a TEC",
		"section": "TEC Report",
		"site": "WINGS",
		"lots": True,
		"parent_label": "TEC",
		"parent_form": "tec_report",
	},
	"stack_status": {"group": "wings", "label": "Stack Status", "section": "Stack Status", "site": "WINGS"},
	"booking_delivery": {
		"group": "wings",
		"label": "Booking / Delivery Status",
		"section": "Booking / Delivery Status",
		"site": "WINGS",
	},
	"targets_paddy": {
		"group": "wings",
		"label": "Targets / Advanced Paddy",
		"section": "Targets / Advanced Paddy",
		"site": "WINGS",
	},
}
# Portal columns that hold only a button: not offered in the grid.
BUTTON_COLUMN = re.compile(r"^(column \d+|action|actions|print)$", re.IGNORECASE)


def _check_access():
	"""Whoever may run Portal Data Extraction may also enter its rows by hand."""
	if not frappe.has_permission("Portal Data Extraction", "create"):
		frappe.throw(_("You are not allowed to enter portal data"), frappe.PermissionError)


def _last_mill(site: str) -> str:
	mill = frappe.db.get_value(
		"Portal Record", {"site": site, "mill_id": ["is", "set"]}, "mill_id", order_by="last_seen_on desc"
	)
	return mill if mill and frappe.db.exists("Mill Master", mill) else ""


def _mill_no(mill_id: str | None) -> str:
	"""The Mill No. of rows entered by hand: required, a mill of Mill Master."""
	mill_id = (mill_id or "").strip()
	if not mill_id:
		frappe.throw(_("Select the Mill No. of these rows"))
	if not frappe.db.exists("Mill Master", mill_id):
		frappe.throw(_("Mill No. {0} is not in Mill Master").format(mill_id))
	return mill_id


def _get_form(form: str) -> dict:
	if form not in MANUAL_FORMS:
		frappe.throw(_("Unknown manual entry form {0}").format(form))
	return MANUAL_FORMS[form]


def _site(config: dict) -> str:
	return config.get("site") or SITE


def _section_row(section: str, site: str | None = None):
	site = site or SITE
	row = frappe.get_cached_doc("Portal Site", site).get_section(section)
	if not row:
		frappe.throw(_("Section {0} is not set up (or disabled) in Portal Site {1}").format(section, site))
	return row


def _common_fields(section) -> list[str]:
	"""Named search filters (e.g. KMS Year) asked once for all rows; "*" (every filter) is not asked."""
	return [name for name, _match in parse_filter_columns(section.filter_columns) if name != "*"]


def _columns(config: dict) -> list[str]:
	if config.get("columns"):
		return config["columns"]
	if config.get("lots"):
		return _detail_columns(config)
	latest = frappe.get_all(
		"Portal Record",
		filters={"site": _site(config), "section": config["section"], "entry_source": "Portal"},
		fields=["row_data"],
		order_by="seen_run desc, row_no asc",
		limit=1,
	)
	cells = json.loads(latest[0].row_data or "{}") if latest else {}
	columns = [h for h in cells if not BUTTON_COLUMN.match(h)]
	if not columns:
		frappe.throw(
			_("Read {0} from the portal once, so the ERP knows its columns. Then rows can be entered by hand.").format(
				config["section"]
			)
		)
	return columns


def _detail_columns(config: dict) -> list[str]:
	"""Columns of the detail rows last read from the portal for this section (e.g. TEC Delivered lines)."""
	parents = frappe.get_all(
		"Portal Record",
		filters={"site": _site(config), "section": config["section"], "details_source": "Portal", "detail_count": [">", 0]},
		pluck="name",
		order_by="seen_run desc",
		limit=1,
	)
	detail = frappe.get_all(
		"Portal Record Detail",
		filters={"parenttype": "Portal Record", "parent": ["in", parents]},
		fields=["detail_data"],
		order_by="line_no asc",
		limit=1,
	)
	columns = list(json.loads(detail[0].detail_data or "{}")) if detail else []
	if not columns:
		frappe.throw(
			_("Read {0} with its detail rows from the portal once, so the ERP knows their columns.").format(
				config["section"]
			)
		)
	return columns


@frappe.whitelist()
def get_manual_forms(group: str = "rrc") -> list[dict]:
	_check_access()
	return [
		{"form": key, "label": _(form["label"])} for key, form in MANUAL_FORMS.items() if form["group"] == group
	]


@frappe.whitelist()
def get_manual_form(form: str) -> dict:
	"""Columns of the grid, the key columns that must be filled, and the
	search filters (e.g. KMS Year, Depot Name) asked once for all rows."""
	_check_access()
	config = _get_form(form)
	section = _section_row(config["section"], _site(config))
	lots = bool(config.get("lots"))
	return {
		"form": form,
		"label": _(config["label"]),
		"section": config["section"],
		"columns": _columns(config),
		"key_columns": [] if lots else parse_key_columns(section.key_columns),
		"common_fields": [] if lots else _common_fields(section),
		"lots": lots,
		"parent_label": _(config.get("parent_label") or ""),
		# Mill No. of the rows: the mill of the site's latest saved row, changeable on the form.
		"mill_id": _last_mill(_site(config)),
	}


@frappe.whitelist()
def get_parent_rows(form: str, txt: str = "") -> list[dict]:
	"""Rows in the ERP (read from the portal or entered by hand) whose detail rows
	the form enters, e.g. DC NO.s of DC Monitoring, TECs of the WINGS TEC Report.
	A section with Key Columns is picked by its key (DC NO.), else by the row's summary."""
	_check_access()
	config = _get_form(form)
	section = _section_row(config["section"], _site(config))
	keyed = bool(parse_key_columns(section.key_columns))
	txt = f"%{(txt or '').strip()}%"
	rows = frappe.get_list(
		"Portal Record",
		filters={"site": _site(config), "section": config["section"]},
		or_filters={"record_key": ["like", txt], "summary": ["like", txt]},
		fields=["name", "record_key", "summary"],
		order_by="seen_run desc, row_no asc",
		limit=50,
	)
	if keyed:
		return [{"label": r.record_key, "value": r.record_key} for r in rows]
	return [{"label": r.summary or r.name, "value": r.name} for r in rows]


@frappe.whitelist(methods=["POST"])
def save_manual_rows(form: str, rows, common=None, mill_id: str | None = None) -> dict:
	"""Save pasted rows of one section. ``rows``: [{column: value}];
	``common``: values for every row (e.g. KMS Year, Depot Name); ``mill_id``: the
	Mill No. (Mill Master) of the rows, required."""
	_check_access()
	config = _get_form(form)
	if config.get("lots"):
		frappe.throw(_("Use the lots form to save the lots of a DC"))
	site = _site(config)
	section = _section_row(config["section"], site)
	# Without Key Columns a row is matched on all its values (as when read from the portal).
	key_columns = parse_key_columns(section.key_columns)

	rows = _parse_rows(rows, _columns(config))
	common = _parse_common(common, section)
	site_doc = frappe.get_cached_doc("Portal Site", site)
	mill = frappe._dict(
		mill_id=_mill_no(mill_id),
		label_keys=mill_label_keys(site_doc.get("mill_id_labels")),
	)
	seen_run = now_datetime()
	result = {"inserted": 0, "updated": 0, "skipped": 0, "errors": []}
	keys_done = set()
	for row_no, cells in rows:
		save_point = f"manual_row_{row_no}"
		frappe.db.savepoint(save_point)
		try:
			outcome = _save_manual_row(site, section, key_columns, {**common, **cells}, row_no, seen_run, keys_done, mill)
		except Exception as e:
			frappe.db.rollback(save_point=save_point)
			frappe.clear_last_message()
			result["errors"].append(_("Row {0}: {1}").format(row_no, str(e) or type(e).__name__))
			continue
		frappe.db.release_savepoint(save_point)
		if isinstance(outcome, str):
			result[outcome] += 1
		else:
			result["skipped"] += 1
			result["errors"].append(_("Row {0}: {1}").format(row_no, outcome[1]))
	return result


def _save_manual_row(site, section, key_columns, cells, row_no, seen_run, keys_done, mill=None):
	cells = fix_section_cells(section.section_name, normalize_cells(cells))
	by_header = {h.lower(): v for h, v in cells.items()}
	missing = [c for c in key_columns if not by_header.get(c.lower())]
	if missing:
		frappe.throw(_("fill {0}").format(", ".join(missing)))

	record_key = build_record_key(cells, key_columns)
	shown_key = build_summary(cells, key_columns)
	if record_key in keys_done:
		return ("skipped", _("{0} is pasted twice; the first row is kept").format(shown_key))
	keys_done.add(record_key)

	mill = mill or frappe._dict(mill_id="", label_keys=mill_label_keys(None))
	mill_id = row_mill_id(cells, mill.label_keys, mill.mill_id)
	name = resolve_record_name(site, section.section_name, record_key, mill_id)
	values = {
		"mill_id": mill_id,
		"row_data": json.dumps(cells, ensure_ascii=False),
		"row_hash": build_row_hash(cells),
		"summary": build_summary(cells, key_columns),
		"last_seen_on": now_datetime(),
		"seen_run": seen_run,
		"row_no": row_no,
		"entry_source": "Manual",
	}
	if frappe.db.exists("Portal Record", name):
		doc = frappe.get_doc("Portal Record", name)
		if doc.entry_source != "Manual":
			return ("skipped", _("{0} was read from the portal; portal data has priority").format(shown_key))
		doc.update(values)
		doc.save(ignore_permissions=True)
		return "updated"

	doc = frappe.new_doc("Portal Record")
	doc.name = name
	doc.update(
		{
			"site": site,
			"section": section.section_name,
			"record_key": record_key,
			"first_seen_on": values["last_seen_on"],
			**values,
		}
	)
	doc.insert(ignore_permissions=True)
	return "inserted"


@frappe.whitelist(methods=["POST"])
def save_manual_lots(dc_no: str | None = None, rows=None, form: str = "dc_lots", parent: str | None = None) -> dict:
	"""Save the pasted detail rows of one parent row: the lots of a DC (by DC NO.),
	the Delivered lines of a TEC (by the record picked). A "Total" line becomes the footer."""
	_check_access()
	config = _get_form(form)
	if not config.get("lots"):
		frappe.throw(_("Form {0} does not enter detail rows").format(form))
	site = _site(config)
	section = _section_row(config["section"], site)
	parent = (parent or dc_no or "").strip()
	label = _(config["parent_label"])
	if not parent:
		frappe.throw(_("Enter the {0} first").format(label))

	# Picked by key (DC NO.) or, in a section without Key Columns, by the record itself.
	name = frappe.db.get_value(
		"Portal Record", {"site": site, "section": section.section_name, "record_key": parent}, "name"
	)
	if not name:
		by_name = frappe.db.get_value("Portal Record", parent, ["site", "section"], as_dict=True)
		if not by_name or (by_name.site, by_name.section) != (site, section.section_name):
			frappe.throw(
				_("{0} {1} is not in the ERP. Read it from the portal, or add it first in Manual Entry: {2}.").format(
					label, parent, _(MANUAL_FORMS[config["parent_form"]]["label"])
				)
			)
		name = parent
	doc = frappe.get_doc("Portal Record", name)
	doc.check_permission("read")
	shown = doc.summary or parent
	if doc.details_source == "Portal" or (not doc.details_source and cint(doc.detail_count)):
		frappe.throw(_("The detail rows of {0} {1} were read from the portal; portal data has priority").format(label, shown))

	lots, footer = [], []
	for _row_no, cells in _parse_rows(rows, _columns(config)):
		is_total = any(TOTAL_CELL.match(v or "") for v in cells.values())
		(footer if is_total else lots).append(cells)
	lots = normalize_details(lots)
	footer = normalize_details(footer)
	if not lots:
		frappe.throw(_("Paste at least one lot"))

	_set_details(doc, lots)
	doc.detail_count = len(lots)
	doc.details_footer = json.dumps(footer, ensure_ascii=False)
	doc.details_hash = build_details_hash(lots + footer)
	doc.details_source = "Manual"
	doc.save(ignore_permissions=True)
	return {"dc_no": shown, "parent": shown, "lots": len(lots), "section": section.section_name}


def _parse_rows(rows, columns: list[str]) -> list[tuple[int, dict]]:
	"""[(row no., {column: value})] of the non-empty rows; only the form's columns are kept."""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(rows, list):
		frappe.throw(_("Rows must be a list"))
	if len(rows) > MAX_MANUAL_ROWS:
		frappe.throw(_("Save at most {0} rows at a time").format(MAX_MANUAL_ROWS))
	out = []
	for row_no, row in enumerate(rows, start=1):
		if not isinstance(row, dict):
			continue
		cells = {c: str(row.get(c) or "").strip() for c in columns}
		if any(cells.values()):
			out.append((row_no, cells))
	if not out:
		frappe.throw(_("Paste or type at least one row"))
	return out


def _parse_common(common, section) -> dict:
	common = frappe.parse_json(common) if isinstance(common, str) else (common or {})
	names = _common_fields(section)
	return {name: str(common.get(name) or "").strip() for name in names if str(common.get(name) or "").strip()}
