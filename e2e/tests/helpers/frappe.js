// Copyright (c) 2026, Profezzo and contributors
// Small helpers for driving Frappe desk pages in Playwright tests.

const { expect } = require("@playwright/test");

// Sites where tests must never save anything (client data).
const PROTECTED_SITES = (process.env.E2E_PROTECTED_SITES || "shyamji")
	.split(",")
	.map((s) => s.trim())
	.filter(Boolean);

function slug(doctype) {
	return doctype.toLowerCase().replace(/ /g, "-");
}

// Wait until the desk has booted (frappe.boot loaded, no pending requests).
async function waitForDesk(page) {
	await page.waitForFunction(() => window.frappe && frappe.boot && frappe.boot.sitename, null, {
		timeout: 30_000,
	});
	await waitAjax(page);
}

async function waitAjax(page) {
	await page.waitForLoadState("networkidle");
	await page.evaluate(() => new Promise((resolve) => frappe.after_ajax(() => resolve())));
}

async function bootInfo(page) {
	return page.evaluate(() => ({ site: frappe.boot.sitename, user: frappe.session.user }));
}

// Server call as the logged-in user (read-only methods only in safe tests).
async function call(page, method, args = {}) {
	return page.evaluate(([m, a]) => frappe.xcall(m, a), [method, args]);
}

async function getList(page, doctype, fields, filters = [], limit = 1) {
	return call(page, "frappe.client.get_list", {
		doctype,
		fields,
		filters,
		limit_page_length: limit,
	});
}

// Open an unsaved new form. Nothing is written until Save is pressed.
async function openNewForm(page, doctype) {
	await page.goto(`/desk/${slug(doctype)}/new`);
	await waitForDesk(page);
	await page.waitForFunction(
		(dt) => window.cur_frm && cur_frm.doctype === dt && cur_frm.is_new(),
		doctype,
		{ timeout: 30_000 }
	);
	await closeDialogs(page);
}

// Type into a Data field like a user (fires the form's change handlers on blur).
async function typeField(page, fieldname, value) {
	const input = page.locator(`.frappe-control[data-fieldname="${fieldname}"] input:visible`).first();
	await input.fill(String(value));
	await input.press("Tab");
	await waitAjax(page);
}

// Set a value through the form API (used for date/time fields, whose typed format depends on settings).
async function setValue(page, fieldname, value) {
	await page.evaluate(([f, v]) => cur_frm.set_value(f, v), [fieldname, value]);
	await waitAjax(page);
}

async function docValue(page, fieldname) {
	return page.evaluate((f) => cur_frm.doc[f], fieldname);
}

// Text of the open message dialog (msgprint), or "" when none is open.
async function dialogText(page) {
	const dialog = page.locator(".modal.show .modal-body").last();
	if (!(await dialog.isVisible().catch(() => false))) return "";
	return (await dialog.innerText()).trim();
}

async function closeDialogs(page) {
	for (let i = 0; i < 3 && (await page.locator(".modal.show").count()); i++) {
		await page.keyboard.press("Escape");
		await page.waitForTimeout(300);
	}
}

// Attach a named screenshot to the HTML report.
async function snap(page, testInfo, name) {
	await testInfo.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
}

// Collect uncaught page errors; call expectNoErrors() at the end of a test.
function trackPageErrors(page) {
	const errors = [];
	page.on("pageerror", (error) => errors.push(String(error)));
	return {
		errors,
		expectNoErrors: () => expect(errors, "uncaught JavaScript errors on the page").toEqual([]),
	};
}

// Safety net for tests that save: refuse protected (client) sites unless explicitly allowed.
async function assertWritesAllowed(page, test) {
	const { site } = await bootInfo(page);
	test.skip(process.env.E2E_ALLOW_WRITES !== "1", "Saving tests run only with E2E_ALLOW_WRITES=1 on a test site.");
	// A protected site is written only with an explicit, approved opt-in naming that exact site.
	const protectedOptIn = process.env.E2E_ALLOW_PROTECTED_SITE === site;
	test.skip(
		PROTECTED_SITES.includes(site) && !protectedOptIn,
		`Site "${site}" is protected (client data). Use a test site, or set E2E_ALLOW_PROTECTED_SITE=${site} after approval.`
	);
	return site;
}

module.exports = {
	PROTECTED_SITES,
	assertWritesAllowed,
	bootInfo,
	call,
	closeDialogs,
	dialogText,
	docValue,
	getList,
	openNewForm,
	setValue,
	slug,
	snap,
	trackPageErrors,
	typeField,
	waitAjax,
	waitForDesk,
};
