// Copyright (c) 2026, Profezzo and contributors
// Full procurement flow through the browser, saving real records:
// PPAS Transit Pass -> Gate Entry -> Quality Check -> RST Details (creates Weigh Bridge)
// -> no GRN while the truck is inside -> Gate Exit -> GRN Note created.
//
// SAVES DATA. Runs only with E2E_ALLOW_WRITES=1 on a site not listed in
// E2E_PROTECTED_SITES (default "shyamji"). Records are tagged E2E-<time> and are not deleted.

const { test, expect } = require("@playwright/test");
const {
	assertWritesAllowed,
	call,
	docValue,
	openNewForm,
	setValue,
	snap,
	waitAjax,
	waitForDesk,
} = require("./helpers/frappe");
const { findSeasonAndTransitPass } = require("./helpers/test-data");

test.describe.configure({ mode: "serial" });

const RUN = `E2E-${Date.now().toString(36).toUpperCase()}`;
const VEHICLE = `${RUN}-TRUCK`;
const state = {};

test.beforeEach(async ({ page }) => {
	await page.goto("/desk");
	await waitForDesk(page);
	await assertWritesAllowed(page, test);
	if (!state.data) {
		state.data = await findSeasonAndTransitPass(page);
	}
	test.skip(!state.data, "No Season Master with dates that has a PPAS Transit Pass on this site.");
});

async function now(page) {
	return page.evaluate(() => frappe.datetime.now_datetime());
}

async function setValues(page, values) {
	for (const [field, value] of Object.entries(values)) {
		await setValue(page, field, value);
	}
}

async function addRow(page, table, values) {
	await page.evaluate(
		([t, v]) => {
			const row = cur_frm.add_child(t);
			Object.assign(row, v);
			cur_frm.refresh_field(t);
		},
		[table, values]
	);
}

// Save the open form and return its name.
async function save(page) {
	await page.evaluate(() => cur_frm.save());
	await waitAjax(page);
	await expect.poll(() => page.evaluate(() => !cur_frm.is_new() && !cur_frm.is_dirty())).toBeTruthy();
	return docValue(page, "name");
}

async function getValue(page, doctype, filters, field) {
	const result = await call(page, "frappe.client.get_value", { doctype, filters, fieldname: field });
	return result && result[field];
}

test("1. Gate Entry (In) for a test truck", async ({ page }, testInfo) => {
	await openNewForm(page, "Gate Entry");
	await setValues(page, {
		in_out: "In",
		in_purpose: "Paddy",
		going_to_weighment: 1,
		vehicle_no: VEHICLE,
		driver_name: `${RUN} Driver`,
		party_name: `${state.data.ppcName}(${state.data.ppcCode})`,
		entry_datetime: await now(page),
	});
	state.gateEntry = await save(page);
	await snap(page, testInfo, "gate-entry");
	expect(await docValue(page, "inside_mill")).toBe(1);
});

test("2. Quality Check is Accepted", async ({ page }, testInfo) => {
	await openNewForm(page, "Quality Check");
	await setValues(page, {
		vehicle_no: VEHICLE,
		gate_entry: state.gateEntry,
		qc_datetime: await now(page),
		driver_name: `${RUN} Driver`,
		paddy_quality: "Mota",
		staff_name: `${RUN} Inspector`,
		unloading_point: "Shed 1",
		paddy_received_in_pkt: 10,
		paddy_returned: 0,
	});
	await addRow(page, "old_new_bags", { new_bags: 10, old_bags: 0 });
	await addRow(page, "type_of_pkt", { no_of_plastic_bag: 10, jute_pkt_no: 0 });
	state.qualityCheck = await save(page);
	await snap(page, testInfo, "quality-check");
	expect(await docValue(page, "qc_decision")).toBe("Accepted");
});

test("3. RST Details: TP Received, Season Code, RST Unique Key, Weigh Bridge created", async ({ page }, testInfo) => {
	const { data } = state;
	await openNewForm(page, "RST Details");
	await setValues(page, {
		rst_no: `${RUN}-RST`,
		entry_datetime: data.rstDatetime,
		vehicle_no: VEHICLE,
		party_name: `${data.ppcName}(${data.ppcCode})`,
		tp_no: data.pass.transit_pass_no,
		gross_vehicle_weight_qt: 300,
		tare_vehicle_weight_qt: 100,
		gunny_weight_qt: 0,
		deduction_qt: 2,
		commodity: "Paddy",
	});
	state.rst = await save(page);
	await page.reload();
	await waitForDesk(page);
	await snap(page, testInfo, "rst-saved");

	expect(await docValue(page, "tp_status")).toBe("TP Received");
	expect(await docValue(page, "season_code")).toBe(data.season.season_code);
	expect(await docValue(page, "rst_unique_key")).toBe(data.pass.pass_unique_key);
	state.weighBridge = await docValue(page, "weigh_bridge_measurement");
	expect(state.weighBridge, "Weigh Bridge Measurement linked to the RST").toBeTruthy();
});

test("4. No GRN while the truck is still inside the mill", async ({ page }) => {
	const grn = await getValue(page, "GRN Note", { weigh_bridge_measurement: state.weighBridge }, "name");
	expect(grn, "GRN must wait for Gate Exit").toBeFalsy();
});

test("5. Gate Exit creates the GRN Note", async ({ page }, testInfo) => {
	await openNewForm(page, "Gate Exit");
	await setValues(page, {
		out_purpose: "Others",
		vehicle_no: VEHICLE,
		gate_entry_in: state.gateEntry,
		exit_datetime: await now(page),
	});
	state.gateExit = await save(page);
	await snap(page, testInfo, "gate-exit");

	await expect
		.poll(() => getValue(page, "GRN Note", { weigh_bridge_measurement: state.weighBridge }, "name"))
		.toBeTruthy();
	const grn = await getValue(page, "GRN Note", { weigh_bridge_measurement: state.weighBridge }, "name");
	await page.goto(`/desk/grn-note/${encodeURIComponent(grn)}`);
	await waitForDesk(page);
	await snap(page, testInfo, "grn-note");
	expect(await docValue(page, "gate_exit")).toBe(state.gateExit);
	expect(await docValue(page, "pass_unique_key")).toBe(state.data.pass.pass_unique_key);
});
