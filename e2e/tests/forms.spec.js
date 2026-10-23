// Copyright (c) 2026, Profezzo and contributors
// Workflow screens open without errors, and empty forms are stopped by validation.
// Read-only: pressing Save on an EMPTY form is blocked in the browser ("Missing Fields"),
// so no request is sent and nothing is created.

const { test, expect } = require("@playwright/test");
const { closeDialogs, openNewForm, slug, snap, trackPageErrors, waitForDesk } = require("./helpers/frappe");

const WORKFLOW = ["PPAS Transit Pass", "Gate Entry", "Weigh Bridge Measurement", "Quality Check", "RST Details", "GRN Note"];

for (const doctype of WORKFLOW) {
	test(`${doctype} list opens`, async ({ page }, testInfo) => {
		const errors = trackPageErrors(page);
		await page.goto(`/desk/${slug(doctype)}`);
		await waitForDesk(page);
		await expect(page.locator(".frappe-list")).toBeVisible();
		await snap(page, testInfo, `${doctype} list`);
		errors.expectNoErrors();
	});
}

for (const [doctype, required] of [
	["Gate Entry", ["Vehicle No", "Party Name"]],
	["RST Details", ["RST No", "Party Name"]],
]) {
	test(`${doctype}: Save on an empty form shows Missing Fields`, async ({ page }, testInfo) => {
		await openNewForm(page, doctype);
		await page.keyboard.press("Control+s");
		const dialog = page.locator(".modal.show").last();
		await expect(dialog).toContainText("Missing Fields");
		for (const label of required) {
			await expect(dialog).toContainText(label);
		}
		await snap(page, testInfo, `${doctype} missing fields`);
		await closeDialogs(page);
		expect(await page.evaluate(() => cur_frm.is_new()), "form must stay unsaved").toBeTruthy();
	});
}
