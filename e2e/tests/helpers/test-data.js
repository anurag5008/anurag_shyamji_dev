// Copyright (c) 2026, Profezzo and contributors
// Finds test data on the site at run time (read-only), so no client data lives in this repo.

const { getList } = require("./frappe");

const PPC_NAME_CODE = /^(.+?)\s*\(([^)]+)\)\s*$/;

// A Season Master with Start/End Date and a PPAS Transit Pass of that season.
async function findSeasonAndTransitPass(page) {
	const seasons = await getList(
		page,
		"Season Master",
		["name", "season_code", "start_date", "end_date"],
		[["start_date", "is", "set"], ["season_code", "is", "set"]],
		20
	);
	for (const season of seasons) {
		const [pass] = await getList(
			page,
			"PPAS Transit Pass",
			["transit_pass_no", "ppc", "pass_unique_key"],
			[["pass_unique_key", "like", `%-${season.season_code}-TP%`]],
			1
		);
		const parts = pass && PPC_NAME_CODE.exec(pass.ppc || "");
		if (!parts) continue;
		return {
			season,
			pass,
			ppcName: parts[1].trim(),
			ppcCode: parts[2].trim(),
			// RST Date & Time inside the season, so its Season Code applies.
			rstDatetime: `${season.start_date} 10:00:00`,
		};
	}
	return null;
}

module.exports = {
	findSeasonAndTransitPass,
	// Values that cannot exist on a real site.
	UNKNOWN_TP_NO: "E2E-NO-SUCH-TP-0000",
	UNKNOWN_PARTY: "E2E Unknown Farmer",
	DATETIME_OUTSIDE_SEASONS: "1999-01-01 10:00:00",
};
