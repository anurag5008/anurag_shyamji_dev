# Copyright (c) 2026, Profezzo and contributors
"""Vehicle Wise Statement of paddy lifted (with voucher details): the rules, kept apart from the screen so they can be tested.

The statement is made from the PPAS Transit Passes of one Miller and one Season (and, if chosen, one District):
  - one row per vehicle: the quantity of all its passes is added up (a vehicle that comes many times is shown once);
  - Amount = Quantity (quintals) x KM x Rate (per quintal per KM), with the KM and the Rate typed for the vehicle, to the nearest whole rupee;
  - Voucher No: numbered from 1 down the statement; an amount of more than 50,000 gets one voucher for every 50,000 or part of it, and the amount is shared equally by them (more than 50,000: 2 vouchers, more than 1 lakh: 3, more than 1.5 lakh: 4 ...);
  - Payment Mode is Cash for all; Vehicle Type is Own Vehicle when the number is in the Own Vehicle list, else Hired Vehicle.
The District works through the PPC Master: the PPCs of that district are found, and only the passes of those PPCs are used.
"""

import math
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, getdate

VOUCHER_LIMIT = 50000  # a cash voucher is for at most this amount
PAYMENT_MODE = "CASH"
HIRED = "Hired Vehicle"
OWN = "Own Vehicle"


def normal_vehicle(vehicle):
	"""A vehicle number written the same way every time: capitals, no spaces."""
	return re.sub(r"\s+", "", (vehicle or "").upper())


def code_of(text):
	"""The code in brackets at the end of a PPAS name, for example 'GAMBHARI(S1050406)' gives 'S1050406'."""
	match = re.search(r"\(([^()]*)\)\s*$", text or "")
	return match.group(1).strip() if match else ""


def kms_title(season):
	"""'Kharif(2025)' gives 'KMS 2025-26' (Kharif Marketing Season) and 'Rabi(2025)' gives 'RMS 2025-26' (Rabi Marketing Season)."""
	match = re.match(r"\s*([A-Za-z]+)\s*[\(\s-]*\s*(\d{4})", season or "")
	if not match:
		return season or ""
	year = int(match.group(2))
	prefix = "RMS" if match.group(1).lower().startswith("rabi") else "KMS"
	return f"{prefix} {year}-{str(year + 1)[2:]}"


def amount_of(qty, rate):
	"""Quantity x Rate, to the nearest whole rupee (half a rupee goes up), as the amounts on the client's sheet are whole rupees.
	The KM is only noted for the PPC; the Rate already is for that distance."""
	return float(math.floor(flt(qty) * flt(rate) + 0.5))


def vouchers_needed(amount):
	"""0 for no amount; 1 up to 50,000 (50,000 itself is one voucher); then one more for every 50,000 or part of it."""
	amount = flt(amount, 2)
	if amount <= 0:
		return 0
	return max(1, math.ceil(amount / VOUCHER_LIMIT))


def assign_vouchers(amounts, start=1):
	"""Voucher numbers down the statement, as text like '3,4': a row without an amount gets none and does not use a number."""
	numbers, current = [], start
	for amount in amounts:
		count = vouchers_needed(amount)
		numbers.append(",".join(str(n) for n in range(current, current + count)))
		current += count
	return numbers


def vehicle_rows(passes, own_vehicles=()):
	"""One row per vehicle and PPC from the passes (dicts with vehicle_no, ppc, bags and quantity), in vehicle number then PPC order.
	The bags and the quantity of all the passes of the vehicle for that PPC are added up."""
	own = {normal_vehicle(v) for v in own_vehicles}
	grouped = {}
	for row in passes:
		vehicle = normal_vehicle(row.get("vehicle_no"))
		if not vehicle:
			continue
		ppc = (row.get("ppc") or "").strip()
		entry = grouped.setdefault((vehicle, ppc), {"vehicle_no": vehicle, "ppc": ppc, "trips": 0, "bags": 0, "qty": 0.0})
		entry["trips"] += 1
		entry["bags"] += cint(row.get("bags"))
		entry["qty"] += flt(row.get("quantity"))
	result = []
	for key in sorted(grouped):
		entry = grouped[key]
		entry["qty"] = flt(entry["qty"], 2)
		entry["vehicle_type"] = OWN if key[0] in own else HIRED
		result.append(entry)
	return result


def vehicle_lines(doc):
	"""The table rows added up for each vehicle (the rows of one vehicle are together): the statement and the debit vouchers are one line per vehicle.
	Each line has sl_no, vehicle_no, qty, amount, voucher_no, payment_mode and vehicle_type, with the voucher kept on the vehicle's first row."""
	lines, last = [], None
	for row in doc.get("items") or []:
		vehicle = normal_vehicle(row.vehicle_no)
		if last is None or vehicle != last:
			sl_no = str(row.sl_no or "")
			lines.append(
				frappe._dict(
					sl_no=int(sl_no) if sl_no.isdigit() else 0,
					vehicle_no=row.vehicle_no,
					qty=0.0,
					bags=0,
					amount=0.0,
					voucher_no=row.voucher_no or "",
					payment_mode=row.payment_mode or "",
					vehicle_type=row.vehicle_type,
				)
			)
			last = vehicle
		line = lines[-1]
		line.qty = flt(line.qty + flt(row.qty), 2)
		line.bags += cint(row.get("bags"))
		line.amount = flt(line.amount + flt(row.amount), 2)
	return lines


def ppc_codes_of_district(district):
	"""The codes of the PPCs that the PPC Master puts under the district."""
	return set(frappe.get_all("PPC Master", filters={"district": district}, pluck="code"))


def get_passes(miller, season, district=None):
	"""The PPAS Transit Passes of the Miller and Season, limited to the PPCs of the District when one is chosen."""
	filters = {"miller": miller, "season": season}
	passes = frappe.get_all("PPAS Transit Pass", filters=filters, fields=["vehicle_no", "quantity", "ppc", "bags"], order_by="vehicle_no asc")
	if district:
		codes = ppc_codes_of_district(district)
		if not codes:
			frappe.throw(_("No PPC is linked to the district {0} in the PPC Master.").format(frappe.bold(district)))
		passes = [row for row in passes if code_of(row.get("ppc")) in codes]
	return passes


def ppc_distances(codes):
	"""The Distance (KM) kept in the PPC Master for each PPC code that has one: {code: distance}."""
	codes = [c for c in set(codes) if c]
	if not codes:
		return {}
	rows = frappe.get_all("PPC Master", filters={"code": ["in", codes]}, fields=["code", "distance"])
	return {row.code: flt(row.distance) for row in rows if flt(row.distance)}


def own_vehicle_numbers():
	return frappe.get_all("Own Vehicle", filters={"is_active": 1}, pluck="vehicle_no")


def rupees_in_words(amount):
	"""11191 gives 'Eleven Thousand, One Hundred And Ninety One Only' (Indian way, whole rupees)."""
	from frappe.utils import money_in_words

	words = money_in_words(round(flt(amount)), "INR") or ""
	words = re.sub(r"^INR\s+", "", words).strip()
	words = re.sub(r"\s+only\.?$", "", words, flags=re.I).replace(",", "")
	return f"{words} Only"


def voucher_amounts(amount, count):
	"""An amount is shared equally by its vouchers: more than 50,000 in 2, more than 1 lakh in 3, more than 1.5 lakh in 4 and so on
	(the count comes from vouchers_needed). Whole rupees: 114300 in 3 gives 38100, 38100, 38100; what is left over (rupees that do not
	divide) goes to the last voucher: 100001 in 3 gives 33333, 33333, 33335."""
	amount = round(flt(amount))
	if count <= 1:
		return [amount] if count == 1 else []
	share = amount // count
	return [share] * (count - 1) + [amount - share * (count - 1)]


def voucher_date(start_date, vehicle_index, per_date=4):
	"""The date of a vehicle's vouchers: the start date for the first `per_date` vehicles, the next day for the next `per_date` vehicles, and so on."""
	if not start_date:
		return ""
	per_date = max(1, cint(per_date) or 4)
	return formatdate(add_days(getdate(start_date), vehicle_index // per_date), "dd.mm.yyyy")


def debit_vouchers(doc, start_date=None, per_date=4):
	"""One debit voucher for each voucher number of the statement, in number order: number, vehicle, amount, words, mode and date.
	All the vouchers of a vehicle have the same date; every `per_date` vehicles the date goes to the next day (no start date: no date)."""
	result = []
	vehicle_index = 0
	for row in vehicle_lines(doc):
		numbers = [n.strip() for n in (row.voucher_no or "").split(",") if n.strip()]
		if not numbers:
			continue
		date = voucher_date(start_date, vehicle_index, per_date)
		vehicle_index += 1
		for number, amount in zip(numbers, voucher_amounts(row.amount, len(numbers))):
			result.append(
				{
					"voucher_no": number,
					"vehicle_no": row.vehicle_no,
					"amount": amount,
					"words": rupees_in_words(amount),
					"payment_mode": (row.payment_mode or PAYMENT_MODE).upper(),
					"date": date,
				}
			)
	result.sort(key=lambda v: int(v["voucher_no"]) if v["voucher_no"].isdigit() else 0)
	return result
