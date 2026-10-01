# Copyright (c) 2026, Profezzo and contributors

import unittest

from ivri_od.procurement.doctype.ppas_transit_pass.ppas_import import (
	parse_ppas_tab_paste,
	process_manual_ppas_paste,
	resolve_ppas_season_text,
	split_datetime,
)


SAMPLE_HEADER = (
	"Season\tSl#\tPACS\tPPC\tMiller\tTransit Pass No.\tTransit Pass Date\t"
	"Vehicle No\tDriver Name\tBag\tQuantity\tDelay(In Days)\tAccepted Date\tAction"
)

SAMPLE_ROWS = [
	"Kharif(2025)\t1\tDUDUKA(S1050113)\tDUDUKA(S1050113)\tMILL(M051007)\t142\t"
	"03-Mar-2026 09:40:27\tOD03AB4135\tNarendraKaarn\t456\t197.93\t3\t"
	"06-Mar-2026 10:32:47\tAccepted",
	"Kharif(2025)\t4\tMALMANDA(S1051105)\tMALMANDA(S1051105)\tMILL(M051007)\t345\t"
	"01-Mar-2026 12:02:24\t\tCHABICHATRIA\t216\t94\t11\t12-Mar-2026\tAccepted",
]


class TestPPASManualPaste(unittest.TestCase):
	def test_split_datetime_ppas_format(self):
		date_value, time_value = split_datetime("03-Mar-2026 09:40:27")
		self.assertEqual(date_value, "2026-03-03")
		self.assertEqual(time_value, "09:40:27")

	def test_parse_tab_paste_with_header(self):
		paste = SAMPLE_HEADER + "\n" + "\n".join(SAMPLE_ROWS)
		rows = parse_ppas_tab_paste(paste)
		self.assertEqual(len(rows), 2)
		self.assertEqual(rows[0]["Transit Pass No."], "142")

	def test_resolve_season_from_master_style(self):
		self.assertEqual(resolve_ppas_season_text("Kharif(2025)"), "Kharif(2025)")
		self.assertEqual(resolve_ppas_season_text("Kharif 2025"), "Kharif(2025)")

	def test_process_flags_missing_vehicle(self):
		paste = SAMPLE_HEADER + "\n" + SAMPLE_ROWS[1]
		result = process_manual_ppas_paste("Kharif(2025)", paste)
		self.assertEqual(result["total_records"], 1)
		self.assertEqual(result["failed_records"], 1)
		self.assertIn("Vehicle No is required", result["items"][0]["error_message"])

	def test_process_valid_row(self):
		paste = SAMPLE_HEADER + "\n" + SAMPLE_ROWS[0]
		result = process_manual_ppas_paste("Kharif(2025)", paste)
		self.assertEqual(result["total_records"], 1)
		self.assertEqual(result["failed_records"], 0)
		self.assertEqual(result["items"][0]["row_status"], "Valid")
		self.assertEqual(result["items"][0]["transit_pass_date"], "2026-03-03")
		self.assertEqual(result["items"][0]["transit_pass_time"], "09:40:27")

