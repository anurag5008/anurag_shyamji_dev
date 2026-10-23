// Copyright (c) 2026, Profezzo and contributors
// RST Details: TP status rules, PPC name + code matching, Season Code and RST Unique Key.
// Read-only: every case uses a new, unsaved RST form. Nothing is saved.

const { test, expect } = require("@playwright/test");
const {
	closeDialogs,
	dialogText,
	docValue,
	openNewForm,
	setValue,
	snap,
	trackPageErrors,
	typeField,
	waitForDesk,
} = require("./helpers/frappe");
const {
	DATETIME_OUTSIDE_SEASONS,
	UNKNOWN_PARTY,
	UNKNOWN_TP_NO,
	findSeasonAndTransitPass,
} = require("./helpers/test-data");

let data;

test.beforeAll(async ({ browser }) => {
	const context = await browser.newContext({ storageState: ".auth/user.json" });
	const page = await context.newPage();
	await page.goto("/desk");
	await waitForDesk(page);
	data = await findSeasonAndTransitPass(page);
	await context.close();
});

test.beforeEach(async ({ page }) => {
	test.skip(!data, "No Season Master with dates that has a PPAS Transit Pass on this site.");
	await openNewForm(page, "RST Details");
});

// Fill the RST like a user and wait for the live TP status lookup.
async function fillRst(page, { datetime, party, tpNo }) {
	await setValue(page, "entry_datetime", datetime || data.rstDatetime);
	await typeField(page, "party_name", party);
	await typeField(page, "tp_no", tpNo);
}

async function expectUnsaved(page) {
	expect(await page.evaluate(() => cur_frm.is_new()), "RST must stay unsaved").toBeTruthy();
}

test("TP Received only when PPC name AND code match; Season Code and Unique Key filled", async ({ page }, testInfo) => {
	const errors = trackPageErrors(page);
	await fillRst(page, { party: `${data.ppcName}(${data.ppcCode})`, tpNo: data.pass.transit_pass_no });
	await snap(page, testInfo, "tp-received");

	expect(await docValue(page, "tp_status")).toBe("TP Received");
	expect(await docValue(page, "season_code")).toBe(data.season.season_code);
	// Canonical PPC name + code in the Pass Unique Key format = the pass's own key.
	expect(await docValue(page, "rst_unique_key")).toBe(data.pass.pass_unique_key);
	expect(await dialogText(page)).toBe("");
	await expectUnsaved(page);
	errors.expectNoErrors();
});

test("spacing and letter case in Party Name are ignored", async ({ page }) => {
	await fillRst(page, {
		party: `  ${data.ppcName.toLowerCase()}  ( ${data.ppcCode.toLowerCase()} ) `,
		tpNo: ` ${data.pass.transit_pass_no} `,
	});
	expect(await docValue(page, "tp_status")).toBe("TP Received");
	await expectUnsaved(page);
});

for (const [label, party] of [
	["PPC name only", () => data.ppcName],
	["PPC code only", () => data.ppcCode],
	["wrong name with the right code", () => `E2E WRONG(${data.ppcCode})`],
]) {
	test(`PPC Mismatch: ${label}`, async ({ page }, testInfo) => {
		await fillRst(page, { party: party(), tpNo: data.pass.transit_pass_no });
		await snap(page, testInfo, `mismatch-${label}`);

		expect(await docValue(page, "tp_status")).toBe("PPC Mismatch");
		expect(await dialogText(page)).toContain("Enter Correct PPC Name.");
		expect(await docValue(page, "rst_unique_key")).toBeFalsy();
		await closeDialogs(page);
		await expectUnsaved(page);
	});
}

test("Invalid TP No takes priority over PPC checks", async ({ page }, testInfo) => {
	await fillRst(page, { party: `${data.ppcName}(${data.ppcCode})`, tpNo: UNKNOWN_TP_NO });
	await snap(page, testInfo, "invalid-tp");

	expect(await docValue(page, "tp_status")).toBe("Invalid TP No");
	expect(await dialogText(page)).toContain("Invalid TP No.");
	await closeDialogs(page);
	await expectUnsaved(page);
});

test("TP No Not Received: no TP No, Party Name is a known PPC", async ({ page }) => {
	await fillRst(page, { party: `${data.ppcName}(${data.ppcCode})`, tpNo: "" });
	expect(await docValue(page, "tp_status")).toBe("TP No Not Received");
	expect(await docValue(page, "season_code")).toBe(data.season.season_code);
	await expectUnsaved(page);
});

test("Local Paddy Purchase: no TP No, unknown party", async ({ page }) => {
	await fillRst(page, { party: UNKNOWN_PARTY, tpNo: "" });
	expect(await docValue(page, "tp_status")).toBe("Local Paddy Purchase");
	await expectUnsaved(page);
});

test("Season Not Configured: RST date outside every season", async ({ page }, testInfo) => {
	await fillRst(page, {
		datetime: DATETIME_OUTSIDE_SEASONS,
		party: `${data.ppcName}(${data.ppcCode})`,
		tpNo: data.pass.transit_pass_no,
	});
	await snap(page, testInfo, "season-not-configured");

	expect(await docValue(page, "season_code")).toBeFalsy();
	expect(await docValue(page, "rst_unique_key")).toBeFalsy();
	// frm.set_intro() is shown as the form message bar in Frappe v16. On a live lookup the
	// server's reason is shown; "Season Not Configured" is the wording for a saved RST.
	await expect(page.locator(".form-message-container .form-message").first()).toContainText(
		"No Season Master covers the RST Date & Time"
	);
	await expectUnsaved(page);
});
