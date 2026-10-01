# Copyright (c) 2026, Profezzo and contributors

import base64
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import format_datetime, get_url_to_form, now_datetime
from frappe.utils.jinja import get_jenv
from frappe.utils.pdf import get_pdf


def get_company_name() -> str:
	company = frappe.defaults.get_global_default("company")
	if not company:
		return ""
	return frappe.db.get_value("Company", company, "company_name") or company


def _qr_line(label: str, value) -> str | None:
	text = ("" if value is None else str(value)).strip()
	if not text or text == "—":
		return None
	return f"{label}: {text}"


def _join_qr_lines(*parts: str | None) -> str:
	return "\n".join(line for line in parts if line)


def qr_content_gate_entry(doc, entry_datetime_display: str) -> str:
	"""All main Gate Entry fields as plain text for phone QR scanners."""
	movement = doc.in_out or "In"
	lines = [
		_qr_line("Gate Entry", doc.name),
		_qr_line("Movement", movement),
		_qr_line("Vehicle No", doc.vehicle_no),
		_qr_line("Driver", doc.driver_name),
		_qr_line("Mobile", doc.mobile_no),
		_qr_line("Gate In Date & Time", entry_datetime_display),
	]
	if movement == "In":
		lines.extend(
			[
				_qr_line("Purpose", doc.in_purpose),
				_qr_line("Purpose Details", doc.purpose),
				_qr_line(
					"Going to Weighment",
					"Yes" if doc.going_to_weighment else "No",
				),
				_qr_line("Inside Mill", "Yes" if doc.inside_mill else "No"),
			]
		)
	else:
		lines.extend(
			[
				_qr_line("Out Purpose", doc.out_purpose),
				_qr_line("Out Purpose Detail", doc.out_purpose_detail),
				_qr_line("Gate Entry In", doc.gate_entry_in),
			]
		)
	body = _join_qr_lines(*lines)
	try:
		body = f"{body}\n\n{get_url_to_form('Gate Entry', doc.name)}"
	except Exception:
		pass
	return body


def qr_content_entry(doc, entry_datetime_display: str) -> str:
	"""All main Entry fields as plain text for phone QR scanners."""
	lines = [
		_qr_line("Entry", doc.name),
		_qr_line("Date & Time", entry_datetime_display),
		_qr_line("TP Pass Key", doc.pass_unique_key),
		_qr_line("Transit Pass No", doc.transit_pass_no),
		_qr_line("PACS Name", doc.pacs_name),
		_qr_line("TP Quantity", doc.tp_quantity),
		_qr_line("Agent Name", doc.agent_name),
		_qr_line("Entry Quantity", doc.entry_quantity),
		_qr_line("Price Per Quintal", doc.entry_price_per_quintal),
		_qr_line("Total Amount", doc.total_amount),
	]
	body = _join_qr_lines(*lines)
	try:
		body = f"{body}\n\n{get_url_to_form('Entry', doc.name)}"
	except Exception:
		pass
	return body


def qr_image_html(data: str, size: int = 168) -> str:
	"""PNG embedded as base64 — scans reliably from PDF (SVG often breaks in wkhtmltopdf)."""
	from pyqrcode import create as qrcreate

	stream = BytesIO()
	# High correction when payload is longer (full details)
	error_level = "H" if len(data) > 200 else "M"
	qrcreate(data, error=error_level).png(
		stream,
		scale=8,
		module_color=[0, 0, 0],
		background=[255, 255, 255],
	)
	b64 = base64.b64encode(stream.getvalue()).decode("ascii")
	return (
		f'<img src="data:image/png;base64,{b64}" width="{size}" height="{size}" '
		f'alt="QR Code" class="qr-image" />'
	)


def render_template_file(relative_parts: tuple[str, ...], context: dict) -> str:
	template_path = frappe.get_app_path("ivri_od", *relative_parts)
	with open(template_path, encoding="utf-8") as template_file:
		template_source = template_file.read()
	env = get_jenv()
	context.setdefault("printed_on", format_datetime(now_datetime()))
	context.setdefault("company_name", get_company_name())
	context.setdefault("_", _)
	return env.from_string(template_source).render(context)


def send_pdf_download(html: str, filename: str) -> None:
	safe_name = filename.replace("/", "-")
	if not safe_name.lower().endswith(".pdf"):
		safe_name += ".pdf"
	frappe.local.response.filename = safe_name
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "download"
