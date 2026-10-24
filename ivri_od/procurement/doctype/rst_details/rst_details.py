import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ivri_od.procurement.datetime_fields import ensure_doc_datetime
from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import (
	MAX_KEY_LENGTH,
	_key_part,
	make_pass_unique_key,
	short_season_code,
)
from ivri_od.procurement.doctype.season_master.season_master import get_season_code, get_season_for_date
from ivri_od.procurement.grn_tp_fulfillment import chhatni_from_rate

from ivri_od.procurement.mill_gate import normalize_vehicle_no
from ivri_od.procurement.transit_pass_resolve import (
	_transit_pass_matches_season,
	find_transit_passes_by_tp_and_ppc,
	get_agent_for_ppc_text,
	mill_id_from_transit_pass,
	normalize_ppc_text,
	ppc_master_candidates,
	resolve_ppc_master_name,
)


RICE_DISPATCH_STATUS = "Rice Dispatch"


class RSTDetails(Document):
	def validate(self):
		ensure_doc_datetime(self, "entry_datetime", date_field="entry_date", time_field="entry_time")
		self._validate_unique_rst_no()
		self._set_tp_status()
		self._set_chhatni()
		self._validate_mill_name()
		self._validate_local_purchase_order()

	def on_trash(self):
		wbm_name = self.weigh_bridge_measurement
		if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
			frappe.delete_doc("Weigh Bridge Measurement", wbm_name, ignore_permissions=True)

	def on_update(self):
		try:
			self._sync_weigh_bridge_measurement()
		except Exception as exc:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"RST Details {self.name}: Weigh Bridge Measurement sync failed",
			)
			frappe.msgprint(
				_("RST Details was saved, but no Weigh Bridge Measurement was created: {0}").format(str(exc)),
				title=_("Transit Pass / Weigh Bridge Error"),
				indicator="red",
				alert=True,
			)

	def _sync_mill_and_agent_from_transit_pass(self):
		"""Kept for backward compatibility; logic handled by _set_tp_status."""
		pass

	def _validate_mill_name(self):
		if self.tp_status == "TP Received" and not (self.mill_name or "").strip():
			frappe.throw(
				_("Mill No could not be fetched from Transit Pass for this Party Name and TP No."),
				title=_("Missing Mill No"),
			)

	def _set_tp_status(self):
		details = resolve_rst_tp_details(self.tp_no, self.party_name, self.entry_datetime or self.entry_date)

		# Ambiguous Transit Pass only: never pick one of several passes.
		if details.get("validation_message"):
			frappe.throw(details["validation_message"], title=_("Transit Pass"))

		self.tp_status = details.get("tp_status") or ""
		# TP Received: keep the PPC Master identity, whatever way the PPC was typed.
		if details.get("party_name"):
			self.party_name = details["party_name"]
		# PPC Mismatch and Invalid TP No are saved; only inform the user.
		if details.get("notification"):
			title = _("Invalid TP No") if self.tp_status == "Invalid TP No" else _("PPC Mismatch")
			frappe.msgprint(details["notification"], title=title, indicator="orange", alert=True)
		# Never keep a mill or agent that the current TP No / Party Name does not resolve.
		self.mill_name = details.get("mill_name") or ""
		self.agent_name = details.get("agent_name") or ""
		self.tp_quantity = flt(details.get("tp_quantity"))
		self._set_season_code_and_rst_unique_key(details)

	def _set_chhatni(self):
		"""Hidden, for future RST-based Chhatni entry; same formulas as the Chhatni DocType.

		Not used by Mandi Book yet: the Chhatni DocType is the active workflow.
		"""
		if not self.meta.has_field("chhatni_qt"):
			return
		values = chhatni_from_rate(self.net_paddy_weight_qt, self.chhatni_kg_per_qtl, self.tp_quantity)
		self.chhatni_kg = values["chhatni_kg"]
		self.chhatni_qt = values["chhatni_qt"]
		self.received_chhatni_pct = values["received_chhatni_pct"]

	def _set_season_code_and_rst_unique_key(self, details):
		# Fields exist only after migrate; until then there is nothing to store.
		if self.meta.has_field("season_code"):
			self.season_code = details.get("season_code") or ""
		if self.meta.has_field("rst_unique_key"):
			self.rst_unique_key = details.get("rst_unique_key") or ""
		# Inform only: the RST saves without a key until the season or Transit Pass is corrected.
		if details.get("key_message"):
			title = _("RST Unique Key") if details.get("season_code") else _("Season Not Configured")
			frappe.msgprint(details["key_message"], title=title, indicator="orange")

	def _validate_unique_rst_no(self):
		rst_no = (self.rst_no or "").strip()
		if not rst_no:
			return

		filters = {"rst_no": rst_no}
		if not self.is_new():
			filters["name"] = ["!=", self.name]

		if frappe.db.exists("RST Details", filters):
			frappe.throw(
				_("RST No {0} already exists. Enter a unique RST No.").format(frappe.bold(rst_no)),
				title=_("Duplicate RST No"),
			)

	def _validate_local_purchase_order(self):
		if not (self.local_purchase_order or "").strip():
			return
		if not frappe.db.exists("Local Paddy Purchase Order", self.local_purchase_order):
			frappe.throw(_("Local Paddy Purchase Order {0} does not exist.").format(self.local_purchase_order))
		po = frappe.db.get_value(
			"Local Paddy Purchase Order",
			self.local_purchase_order,
			["party_name", "status", "commodity"],
			as_dict=True,
		)
		if not po:
			return
		if not (self.commodity or "").strip() and (po.commodity or "").strip():
			self.commodity = po.commodity.strip()
		if self.party_name and po.party_name:
			p1 = self.party_name.strip().lower()
			p2 = po.party_name.strip().lower()
			if p1 not in p2 and p2 not in p1:
				frappe.msgprint(
					_("Warning: Selected Purchase Order party '{0}' does not match RST party '{1}'.").format(
						po.party_name, self.party_name
					),
					indicator="orange",
					alert=True,
				)

	def _sync_weigh_bridge_measurement(self):
		rice_dispatch = self.tp_status == RICE_DISPATCH_STATUS
		private = False if rice_dispatch else is_private_procurement_rst(self)
		awaiting_tp = False if rice_dispatch else party_found_awaiting_tp(self)
		transit_pass = None
		unresolved = False
		if not private and not awaiting_tp and not rice_dispatch:
			transit_pass = try_get_matching_transit_pass(self)
			if not transit_pass:
				has_weighment = bool((self.weigh_bridge_measurement or "").strip())
				# PPC Mismatch is kept in the Weigh Bridge list with its status; Invalid TP No creates nothing.
				if not has_weighment and self.tp_status != "PPC Mismatch":
					return
				# The Weigh Bridge and GRN follow the RST: they must not keep an old pass.
				unresolved = True
				if has_weighment:
					frappe.msgprint(
						_(
							"TP No and Party Name match no Transit Pass. The Weigh Bridge and GRN Note no longer show "
							"a Transit Pass. Correct TP No or Party Name and save again to link it."
						),
						title=_("Transit Pass Removed"),
						indicator="orange",
						alert=True,
					)

		values = {
			"demo_rst_data": self.name,
			"rst_no": self.rst_no,
			"load_weight": flt(self.gross_vehicle_weight_qt),
			"tare_weight": flt(self.tare_vehicle_weight_qt),
			"deduction": flt(self.deduction_qt),
			"gunny_type": "Gunny Cut" if flt(self.gunny_weight_qt) > 0 else "Gunny Gross",
			"gunny_weight": flt(self.gunny_weight_qt),
			"commodity": self.commodity,
			"measurement_date": self.entry_date,
			"measurement_time": self.entry_time,
		}

		if rice_dispatch:
			# No Transit Pass: TP No is the Lot No, kept exactly as entered. RST vehicle goes to
			# Actual Truck No, as for a weighment that has no pass yet.
			rst_vehicle = (self.vehicle_no or "").strip().upper()
			values.update(
				{
					"is_farmer_or_agent": 0,
					"agent_name": "",
					"party_name": (self.party_name or "").strip(),
					"lot_no": self.tp_no or "",
					"same_truck_as_transit_pass": 1 if rst_vehicle else 0,
					"actual_truck_no": rst_vehicle,
					"pass_unique_key": "",
					"vehicle_no": "",
				}
			)
		elif private:
			values.update(
				{
					"is_farmer_or_agent": 1,
					"vehicle_no": "",
					"same_truck_as_transit_pass": 0,
					"actual_truck_no": normalize_vehicle_no(self.vehicle_no),
					"pass_unique_key": "",
					"agent_name": "",
					"party_name": (self.party_name or "").strip(),
					"local_purchase_order": (self.local_purchase_order or "").strip(),
					"purchase_order": (self.local_purchase_order or "").strip(),
				}
			)
		elif awaiting_tp or unresolved:
			# No usable Transit Pass (TP No empty, or it no longer matches). Create the weigh bridge
			# without a mill number or transit pass. RST vehicle goes to Actual Truck No.
			# Mill is fetched when TP No is updated. Whatever an earlier pass had put on it is cleared.
			rst_vehicle = (self.vehicle_no or "").strip().upper()
			values.update(
				{
					"is_farmer_or_agent": 0,
					"agent_name": "",
					"same_truck_as_transit_pass": 1 if rst_vehicle else 0,
					"actual_truck_no": rst_vehicle,
					"pass_unique_key": "",
					"transit_pass_no": "",
					"pacs_name": "",
					"tp_weight": 0,
					"truck_no_in_tp": "",
					"vehicle_no": "",
				}
			)
			if unresolved:
				# Shown in the Weigh Bridge list, so the user sees which party was typed.
				values["party_name"] = (self.party_name or "").strip()
		else:
			tp_vehicle_no = ""
			if transit_pass.pass_unique_key:
				tp_vehicle_no = (
					frappe.db.get_value(
						"PPAS Transit Pass",
						{"pass_unique_key": transit_pass.pass_unique_key},
						"vehicle_no",
					)
					or ""
				)

			rst_v = (self.vehicle_no or "").strip().upper()
			tp_v = (tp_vehicle_no or "").strip().upper()

			if rst_v and tp_v:
				if rst_v == tp_v:
					same_truck = 0
					actual_truck = ""
				else:
					same_truck = 1
					actual_truck = rst_v
			elif rst_v and not tp_v:
				same_truck = 1
				actual_truck = rst_v
			else:
				same_truck = 0
				actual_truck = ""

			values.update(
				{
					"is_farmer_or_agent": 0,
					"agent_name": self.agent_name,
					"same_truck_as_transit_pass": same_truck,
					"actual_truck_no": actual_truck,
					"pass_unique_key": transit_pass.pass_unique_key,
					"vehicle_no": "",
				}
			)

		from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
			compute_wbm_tp_status,
		)

		values["tp_status"] = compute_wbm_tp_status(frappe._dict(values))

		wbm_name = self.weigh_bridge_measurement
		if rice_dispatch and not (wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name)):
			# Never create a second record when the link was lost but this RST already has one.
			wbm_name = frappe.db.get_value("Weigh Bridge Measurement", {"demo_rst_data": self.name}, "name")
			if wbm_name:
				self.db_set("weigh_bridge_measurement", wbm_name, update_modified=False)
		if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
			wbm = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
			for fieldname, value in values.items():
				wbm.set(fieldname, value)
			if awaiting_tp or unresolved:
				wbm.flags.ignore_mandatory = True
			wbm.save(ignore_permissions=True)
		else:
			wbm = frappe.get_doc({"doctype": "Weigh Bridge Measurement", **values})
			if awaiting_tp:
				wbm.flags.ignore_mandatory = True
			wbm.insert(ignore_permissions=True)
			self.weigh_bridge_measurement = wbm.name
			self.db_set("weigh_bridge_measurement", wbm.name, update_modified=False)


_PARTY_NAME_WITH_CODE = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")


def _ppc_text_forms(ppc_text: str | None) -> set[str]:
	"""Texts that mean this PPC: the whole text, its name part and its code part."""
	ppc_text = (ppc_text or "").strip()
	forms = {normalize_ppc_text(ppc_text)}
	parts = _PARTY_NAME_WITH_CODE.match(ppc_text)
	if parts:
		forms.update(normalize_ppc_text(part) for part in parts.groups())
	forms.discard("")
	return forms


def party_ppc_match_state(party_name: str | None, ppc_on_pass: str | None, candidates=None) -> str:
	"""Compare Party Name with the PPC on a Transit Pass: "match", "ambiguous" or "mismatch".

	Party Name may be the PPC name, the code, or name plus code, in any case, spacing or brackets.
	PPC Master decides first. "ambiguous": the text fits several PPC Masters and one of them is the pass PPC.
	`candidates` is ppc_master_candidates(party_name), passed in when many passes are compared.
	"""
	if not normalize_ppc_text(party_name) or not (ppc_on_pass or "").strip():
		return "mismatch"
	if candidates is None:
		candidates = ppc_master_candidates(party_name)
	pass_master = resolve_ppc_master_name(ppc_on_pass)
	if pass_master and candidates:
		if pass_master not in candidates:
			return "mismatch"
		return "match" if len(candidates) == 1 else "ambiguous"
	# Not in PPC Master (or spelled differently there): the pass text itself must say it.
	return "match" if normalize_ppc_text(party_name) in _ppc_text_forms(ppc_on_pass) else "mismatch"


def ppc_name_and_code(ppc_text: str | None) -> tuple[str, str]:
	"""Canonical (PPC name, PPC code): from PPC Master when the text resolves, else its NAME(CODE) parts."""
	master = resolve_ppc_master_name(ppc_text)
	if master:
		ppc_name, code = frappe.db.get_value("PPC Master", master, ["ppc_name", "code"]) or ("", "")
		return " ".join((ppc_name or "").split()), (code or master).strip()
	parts = _PARTY_NAME_WITH_CODE.match((ppc_text or "").strip())
	if parts:
		return " ".join(parts.group(1).split()), parts.group(2).strip()
	return "", ""


def classify_rst_transit_passes(tp_no: str | None, party_name: str | None) -> tuple[list[dict], bool]:
	"""(passes of this TP No that Party Name identifies as their PPC, True when the name fits several PPCs)."""
	candidates = ppc_master_candidates(party_name)
	matching, ambiguous = [], False
	for row in find_transit_passes_by_tp_and_ppc(tp_no, party_name):
		state = party_ppc_match_state(party_name, row.get("ppc"), candidates)
		if state == "match":
			matching.append(row)
		ambiguous = ambiguous or state == "ambiguous"
	return matching, ambiguous


def find_rst_transit_passes(tp_no: str | None, party_name: str | None) -> list[dict]:
	"""Transit Pass rows for this TP No whose PPC Party Name identifies (see party_ppc_match_state)."""
	return classify_rst_transit_passes(tp_no, party_name)[0]


def rst_unique_key_for_pass(row: dict, tp_no: str, season_code: str) -> str:
	"""RST Unique Key in the Pass Unique Key format, with the canonical PPC Master NAME(CODE)."""
	name, code = ppc_name_and_code(row.get("ppc"))
	ppc = f"{name}({code})" if name and code else row.get("ppc")
	return make_pass_unique_key(
		row.get("transit_pass_no") or tp_no, ppc, mill_id_from_transit_pass(row), season_code
	)


def _like_escape(value: str) -> str:
	return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _party_ppc_candidates(party_name: str) -> list[str]:
	"""Texts a Transit Pass PPC may carry for this Party Name (typed text and its PPC Master values)."""
	candidates = [party_name]
	master = resolve_ppc_master_name(party_name)
	if master:
		for value in frappe.db.get_value("PPC Master", master, ["name", "code", "ppc_name"]) or ():
			if (value or "").strip():
				candidates.append(value.strip())
	return list(dict.fromkeys(c.casefold() for c in candidates))


def party_matches_any_transit_pass_ppc(party_name: str | None) -> bool:
	"""True when Party Name is the PPC of any Transit Pass.

	Narrows the Transit Pass PPCs with one query, then confirms each with party_ppc_match_state,
	so name or code alone cannot pick the wrong PPC.
	"""
	party_name = (party_name or "").strip()
	if not party_name:
		return False

	cache = getattr(frappe.local, "_party_matches_any_transit_pass_ppc", None)
	if cache is None:
		cache = {}
		frappe.local._party_matches_any_transit_pass_ppc = cache
	key = party_name.casefold()
	if key in cache:
		return cache[key]

	conditions = []
	values = []
	for candidate in _party_ppc_candidates(party_name):
		escaped = _like_escape(candidate)
		conditions.append("(LOWER(TRIM(ppc)) = %s OR LOWER(ppc) LIKE %s OR LOWER(ppc) LIKE %s)")
		values.extend([candidate, f"{escaped}%(%", f"%({escaped})%"])

	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT ppc FROM `tabPPAS Transit Pass`
		WHERE {" OR ".join(conditions)}
		LIMIT 200
		""",
		values,
		as_dict=True,
	)
	candidates = ppc_master_candidates(party_name)
	found = any(party_ppc_match_state(party_name, row.get("ppc"), candidates) != "mismatch" for row in rows)
	cache[key] = found
	return found


def transit_pass_no_exists(tp_no: str) -> bool:
	return bool(
		frappe.db.sql(
			"""
			SELECT 1 FROM `tabPPAS Transit Pass`
			WHERE UPPER(TRIM(IFNULL(transit_pass_no, ''))) = UPPER(TRIM(%s))
			LIMIT 1
			""",
			tp_no,
		)
	)


def get_depo_for_party(party_name: str | None) -> dict | None:
	"""The Depo Master whose Depo Name equals Party Name, else None.

	Name only: matching never uses the Depo Code. Case and extra spaces are ignored; inactive depos count.
	"""
	key = " ".join((party_name or "").split()).casefold()
	if not key:
		return None
	rows = frappe.db.sql(
		"select name, code, depo_name from `tabDepo Master` where lower(trim(depo_name)) = %s limit 1",
		(key,),
		as_dict=True,
	)
	return rows[0] if rows else None


def party_matches_depo_master(party_name: str | None) -> bool:
	"""True when Party Name equals the Depo Name of any Depo Master record."""
	return bool(get_depo_for_party(party_name))


def rice_dispatch_unique_key(depo: dict, season_code: str, lot_no: str | None) -> str:
	"""RST Unique Key for Rice Dispatch: DEPONAME(CODE)-K25-LOT{lot no}.

	Same layout as a Pass Unique Key, but the Lot No is only a reference: it is never read as a TP number.
	The Lot No part is left out when no Lot No was entered.
	"""
	parts = [
		f"{_key_part(depo.get('depo_name'))}({_key_part(depo.get('code'))})",
		short_season_code(season_code),
	]
	lot = _key_part(lot_no, "")
	if lot:
		parts.append(lot if lot.upper().startswith("LOT") else f"LOT{lot}")
	return "-".join(parts)[:MAX_KEY_LENGTH]


def resolve_rst_tp_details(tp_no: str | None, party_name: str | None, rst_datetime=None) -> dict:
	"""Implement the 5 RST TP & Party Name rules:
	1. TP No. exists in Transit Pass and Party Name identifies its PPC (name, code or name plus code; case, spaces
	   and brackets ignored) -> status TP Received, and Party Name is saved as the PPC Master NAME(CODE).
	   A name that fits several PPCs is never guessed: validation_message asks for NAME(CODE).
	2. TP No. is empty but Party Name matches any Transit Pass PPC -> status TP No Not Received.
	3. TP No. exists but Party Name is not its PPC -> status PPC Mismatch (notification).
	4. TP No. is empty and Party Name matches no Transit Pass PPC -> status Local Paddy Purchase.
	5. TP No. is entered but not found in Transit Pass -> status Invalid TP No (notification).
	   Checked before rule 3, so an unknown TP No is never reported as a PPC mismatch.
	Only several passes matching the same TP No and Party Name set validation_message (save is blocked).

	Checked before the five rules: Party Name equals a Depo Master Depo Name -> status Rice Dispatch,
	whether TP No is empty or not. For Rice Dispatch the TP No is a Lot No / reference number: it is
	never looked up in PPAS Transit Pass, never checked against a PPC and never changed.
	Its Season Code comes from the RST Date & Time only, and its RST Unique Key is
	DEPONAME(CODE)-K25-LOT{lot no} (blank, with the usual message, when no season covers the date).
	With no depo match the rules above apply unchanged.

	Season: the Season Master whose Start Date - End Date covers the RST Date & Time gives season_code.
	RST Unique Key = Pass Unique Key format of the TP Received Transit Pass (canonical PPC name + code)
	when that pass is in this season.
	"""
	tp_no = (tp_no or "").strip()
	party_name = (party_name or "").strip()

	result = {
		"tp_status": "",
		"mill_name": "",
		"agent_name": "",
		"notification": "",
		"validation_message": "",
		"season_code": "",
		"rst_unique_key": "",
		"key_message": "",
		"tp_quantity": 0.0,
		"party_name": "",
	}

	season = get_season_for_date(rst_datetime) if rst_datetime else None
	if season:
		result["season_code"] = get_season_code(season)
	elif rst_datetime:
		result["key_message"] = _(
			"No Season Master covers the RST Date & Time, so Season Code and RST Unique Key are empty. "
			"Set Start Date and End Date in Season Master, then save this RST again."
		)

	if party_name and party_matches_depo_master(party_name):
		# Rice Dispatch: season from the RST date only (set above); TP No is the Lot No, kept as is.
		result["tp_status"] = RICE_DISPATCH_STATUS
		depo = get_depo_for_party(party_name)
		if season and depo:
			result["rst_unique_key"] = rice_dispatch_unique_key(depo, result["season_code"], tp_no)
		return result

	if not tp_no:
		if not party_name:
			result["tp_status"] = ""
			return result
		if party_matches_any_transit_pass_ppc(party_name):
			# Rule 2: TP No. is empty but Party Name matches any Transit Pass PPC -> status TP No Not Received
			result["tp_status"] = "TP No Not Received"
			agent = get_agent_for_ppc_text(party_name)
			if agent:
				result["agent_name"] = agent
		else:
			# Rule 4: TP No. is empty and Party Name matches no Transit Pass PPC -> status Local Paddy Purchase
			result["tp_status"] = "Local Paddy Purchase"
		return result

	# TP No is entered
	matching, ambiguous = classify_rst_transit_passes(tp_no, party_name)
	if len(matching) > 1 and season:
		# The same TP No and PPC can exist in two seasons; the RST Date & Time decides.
		matching = [row for row in matching if _transit_pass_matches_season(row, season)] or matching

	if len(matching) > 1:
		# Never pick the first of several matching passes.
		result["validation_message"] = _(
			"More than one transit pass matches TP No and Party Name. Contact support or refine Party Name."
		)
	elif matching:
		# Rule 1: TP No. exists in Transit Pass and entered Party Name matches its PPC -> status TP Received
		result["tp_status"] = "TP Received"
		row = matching[0]
		result["mill_name"] = mill_id_from_transit_pass(row)
		result["agent_name"] = get_agent_for_ppc_text(row.get("ppc"), party_name) or ""
		name, code = ppc_name_and_code(row.get("ppc"))
		if name and code:
			result["party_name"] = f"{name}({code})"
		result["tp_quantity"] = flt(row.get("quantity"), 3)
		if season and _transit_pass_matches_season(row, season):
			result["rst_unique_key"] = rst_unique_key_for_pass(row, tp_no, result["season_code"])
		elif season:
			result["key_message"] = _(
				"Transit Pass {0} is not in season {1} of the RST Date & Time, so the RST Unique Key is empty. "
				"Check the RST Date & Time or the Season Master dates."
			).format(row.get("pass_unique_key"), result["season_code"])
	elif ambiguous:
		# The text fits several PPC Masters: never guess one.
		result["validation_message"] = _(
			"Party Name fits more than one PPC. Type the PPC name with its code, like NAME(CODE)."
		)
	elif not transit_pass_no_exists(tp_no):
		# Rule 5: TP No. is entered but not found in Transit Pass -> status Invalid TP No
		result["tp_status"] = "Invalid TP No"
		result["notification"] = _(
			"Invalid TP No. {0}: no Transit Pass found with this TP No. Enter the correct TP No."
		).format(tp_no)
	else:
		# Rule 3: TP No. exists but its Transit Pass PPC does not match Party Name -> status PPC Mismatch
		result["tp_status"] = "PPC Mismatch"
		result["notification"] = _("Enter Correct PPC Name.")

	return result


def party_found_awaiting_tp(doc) -> bool:
	"""Party Name is a transit-pass PPC and this RST has no TP No yet."""
	tp_no = (getattr(doc, "tp_no", None) or "").strip()
	party_name = (getattr(doc, "party_name", None) or getattr(doc, "ppc_name", None) or "").strip()
	if tp_no or not party_name:
		return False
	if party_matches_depo_master(party_name):
		return False
	return party_matches_any_transit_pass_ppc(party_name)


def is_private_procurement_rst(doc) -> bool:
	"""Farmer/agent only when Party Name is not a transit-pass PPC and TP No is empty."""
	tp_no = (getattr(doc, "tp_no", None) or "").strip()
	party_name = (getattr(doc, "party_name", None) or getattr(doc, "ppc_name", None) or "").strip()
	if tp_no or not party_name:
		return False
	if party_matches_depo_master(party_name):
		return False
	return not party_matches_any_transit_pass_ppc(party_name)


def is_local_procurement_rst(doc) -> bool:
	return is_private_procurement_rst(doc)


def get_rst_agent_name(demo_rst_data=None, rst_no=None) -> str | None:
	"""Agent from RST only when the party is a transit-pass PPC. Local procurement has no agent."""
	rst_name = (demo_rst_data or "").strip()
	if not rst_name and (rst_no or "").strip():
		rst_name = frappe.db.get_value("RST Details", {"rst_no": (rst_no or "").strip()}, "name")
	if not rst_name or not frappe.db.exists("RST Details", rst_name):
		return None
	rst = frappe.db.get_value(
		"RST Details",
		rst_name,
		["agent_name", "party_name", "tp_no"],
		as_dict=True,
	)
	if not rst:
		return None
	doc = frappe._dict(tp_no=rst.tp_no, party_name=rst.party_name)
	if is_private_procurement_rst(doc):
		return None
	return (rst.agent_name or "").strip() or None


def try_get_matching_transit_pass(doc):
	tp_no = (doc.tp_no or "").strip()
	party_name = (getattr(doc, "party_name", None) or getattr(doc, "ppc_name", None) or "").strip()
	if not tp_no or not party_name:
		return None

	transit_passes = find_rst_transit_passes(tp_no, party_name)
	key = (getattr(doc, "rst_unique_key", None) or "").strip()
	if key and len(transit_passes) > 1:
		# Same TP No and PPC in two seasons: the RST Unique Key is the pass for this RST's season.
		# Each pass is keyed with its own season, so only the pass of the RST's season matches.
		transit_passes = [
			row
			for row in transit_passes
			if key
			in (row.get("pass_unique_key"), rst_unique_key_for_pass(row, tp_no, short_season_code(row.get("season"))))
		] or transit_passes
	if not transit_passes:
		return None
	if len(transit_passes) > 1:
		frappe.throw(
			_("More than one transit pass matches TP No and Party Name. Make Party Name more specific.")
		)
	return frappe._dict(transit_passes[0])


@frappe.whitelist()
def check_private_procurement(tp_no=None, party_name=None):
	return {"is_private": False}


@frappe.whitelist()
def fetch_mill_and_agent_from_tp(tp_no=None, party_name=None, ppc_name=None, entry_datetime=None):
	"""Recalculate TP status, mill, agent, Season Code and RST Unique Key; validate TP vs PPC."""
	party_name = (party_name or ppc_name or "").strip()
	tp_no = (tp_no or "").strip()
	return resolve_rst_tp_details(tp_no, party_name, entry_datetime or None)
