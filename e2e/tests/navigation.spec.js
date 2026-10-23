// Copyright (c) 2026, Profezzo and contributors
// Procurement desk layout and navigation. Read-only: views and clicks, nothing saved.

const { test, expect } = require("@playwright/test");
const { snap, trackPageErrors, waitForDesk } = require("./helpers/frappe");

const SHORTCUTS = [
	"Transit Pass",
	"Gate Entry",
	"Quality Check",
	"RST Details",
	"Weigh Bridge",
	"Gate Exit",
	"GRN Note",
	"Mandi Book",
];
const CARDS = [
	"Masters",
	"Season & targets",
	"Govt portals",
	"Gate & weighing",
	"Receipt & GRN",
	"Summary reports",
	"Registers",
];

function path(page) {
	return new URL(page.url()).pathname;
}

async function open(page, url) {
	await page.goto(url);
	await waitForDesk(page);
}

test("Procurement desk: logo header, 8 shortcuts, balanced cards, no cut-off text", async ({ page }, testInfo) => {
	const errors = trackPageErrors(page);
	await open(page, "/desk/procurement");
	await snap(page, testInfo, "procurement-desk");

	await expect(page.locator(".procurement-logo")).toBeVisible();
	await expect(page.locator(".procurement-title")).toHaveText("Procurement desk");
	const shortcuts = await page.locator(".shortcut-widget-box .widget-title").allInnerTexts();
	expect(shortcuts.map((s) => s.trim())).toEqual(SHORTCUTS);
	const cards = await page.locator(".links-widget-box .widget-title").allInnerTexts();
	expect(cards.map((s) => s.trim())).toEqual(CARDS);
	await expect(page.locator(".portal-card-title")).toHaveText("Portal reports");

	const heights = await page.$$eval(".links-widget-box", (els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
	expect(new Set(heights).size, `card heights ${heights}`).toBe(1);
	const cutOff = await page.$$eval(".shortcut-widget-box .widget-title, .links-widget-box .link-text", (els) =>
		els.filter((e) => e.scrollWidth > e.clientWidth + 1).map((e) => e.innerText)
	);
	expect(cutOff).toEqual([]);
	errors.expectNoErrors();
});

test("Portal reports > PPAS Transit Pass opens PPAS Details", async ({ page }, testInfo) => {
	await open(page, "/desk/procurement");
	await page.locator("a.portal-link", { hasText: "PPAS Transit Pass" }).click();
	await waitForDesk(page);
	await snap(page, testInfo, "ppas-details");
	expect(path(page)).toBe("/desk/ppas-details");
	await expect(page.locator(".manual-entry-button")).toBeVisible();
});

test("PPAS Details shows the Procurement sidebar", async ({ page }, testInfo) => {
	await open(page, "/desk/ppas-details");
	await snap(page, testInfo, "ppas-details-sidebar");
	await expect(page.locator(".body-sidebar").getByText("Procurement Home")).toBeVisible();
});

test("Manual Entry > PPAS Transit Pass Import: breadcrumb and browser Back return to PPAS Details", async ({ page }, testInfo) => {
	await open(page, "/desk/ppas-details");
	await page.locator(".manual-entry-button").click();
	await page.getByText("PPAS Transit Pass Import (Manual)").click();
	await waitForDesk(page);
	await snap(page, testInfo, "import-form");
	expect(path(page)).toMatch(/^\/desk\/ppas-transit-pass-import\/new-/);
	await expect(page.locator(".navbar-breadcrumbs a:visible", { hasText: "PPAS Details" }).first()).toBeVisible();

	await page.goBack();
	await waitForDesk(page);
	expect(path(page)).toBe("/desk/ppas-details");

	await page.locator(".manual-entry-button").click();
	await page.getByText("PPAS Transit Pass Import (Manual)").click();
	await waitForDesk(page);
	await page.locator(".navbar-breadcrumbs a:visible", { hasText: "PPAS Details" }).first().click();
	await waitForDesk(page);
	expect(path(page)).toBe("/desk/ppas-details");
});

test("Portal Data Extraction > Add > PPAS: breadcrumb and browser Back return to the list", async ({ page }, testInfo) => {
	await open(page, "/desk/portal-data-extraction");
	await page.getByRole("button", { name: "Add" }).first().click();
	const items = await page.locator(".dropdown-menu.show .dropdown-item").allInnerTexts();
	expect(items.map((s) => s.trim())).toEqual(expect.arrayContaining(["DCRO", "SCMS", "WINGS", "PPAS"]));
	await snap(page, testInfo, "portal-add-menu");

	await page.locator(".dropdown-menu.show .dropdown-item", { hasText: "PPAS" }).click();
	await waitForDesk(page);
	expect(path(page)).toMatch(/^\/desk\/ppas-data-extraction\/new-/);
	await expect(page.locator(".navbar-breadcrumbs a:visible", { hasText: "Portal Data Extraction" }).first()).toBeVisible();

	await page.goBack();
	await waitForDesk(page);
	expect(path(page)).toBe("/desk/portal-data-extraction");
});
