// Copyright (c) 2026, Profezzo and contributors
// Full approved procurement run from evidence/<run>/plan.json (made by tools/plan_full_run.py).
// SAVES records through the normal forms (all validations run). Never deletes anything.
// Every saved document is logged at once to ledger.jsonl; every check to checks.jsonl.
//
// Needs: E2E_RUN_DIR=<evidence dir>, E2E_ALLOW_WRITES=1, and for a protected site
// E2E_ALLOW_PROTECTED_SITE=<site> (explicit approval).

const fs = require("fs");
const path = require("path");
const { test, expect } = require("@playwright/test");
const { assertWritesAllowed, call, closeDialogs, dialogText, docValue, openNewForm, setValue, waitAjax, waitForDesk } =
	require("./helpers/frappe");

const RUN_DIR = process.env.E2E_RUN_DIR || "";
const plan = RUN_DIR && fs.existsSync(path.join(RUN_DIR, "plan.json"))
	? JSON.parse(fs.readFileSync(path.join(RUN_DIR, "plan.json"), "utf8"))
	: null;
const RUN = plan ? plan.run_id : "";
const SHOTS = path.join(RUN_DIR || ".", "screenshots");

test.describe.configure({ mode: "serial" });

function log(file, record) {
	fs.appendFileSync(path.join(RUN_DIR, file), JSON.stringify({ run_id: RUN, at: new Date().toISOString(), ...record }) + "\n");
}

function ledger(tp, step, doctype, name, extra = {}) {
	log("ledger.jsonl", {
		test_id: tp ? tp.id : "",
		step,
		doctype,
		name,
		tp_no: tp ? tp.tp_no : "",
		pass_unique_key: tp ? tp.pass_unique_key : "",
		ppc: tp ? tp.ppc_on_pass : "",
		season: tp ? tp.season : "",
		...extra,
	});
}

// Record a check without stopping the chain (soft assertion).
function check(testId, name, expected, actual, detail = "") {
	const pass = typeof expected === "number" ? Math.abs(Number(actual) - expected) < 0.0005 : expected === actual;
	log("checks.jsonl", { test_id: testId, check: name, expected, actual, pass, detail });
	expect.soft(actual, `${testId}: ${name}`).toEqual(expected);
	return pass;
}

async function shot(page, name) {
	fs.mkdirSync(SHOTS, { recursive: true });
	await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

async function now(page) {
	return page.evaluate(() => frappe.datetime.now_datetime());
}

async function setValues(page, values) {
	for (const [field, value] of Object.entries(values)) {
		await setValue(page, field, value);
	}
}

async function setChildRow(page, table, values) {
	await page.evaluate(
		([t, v]) => {
			cur_frm.clear_table(t);
			Object.assign(cur_frm.add_child(t), v);
			cur_frm.refresh_field(t);
		},
		[table, values]
	);
}

// Save the open form. Returns the document name, or throws with the message the user would see.
async function save(page) {
	await page.evaluate(() => cur_frm.save().catch(() => null));
	await waitAjax(page);
	for (let i = 0; i < 40; i++) {
		const state = await page.evaluate(() => ({ isNew: cur_frm.is_new(), dirty: cur_frm.is_dirty(), name: cur_frm.doc.name }));
		if (!state.isNew && !state.dirty) {
			await closeDialogs(page);
			return state.name;
		}
		// A new document still unsaved, with a message dialog open: the server rejected the save.
		const message = await dialogText(page);
		if (message && state.isNew && i > 3) {
			const title = await page.locator(".modal.show .modal-title").last().innerText().catch(() => "");
			throw new Error(`${title}: ${message}`.slice(0, 500));
		}
		await page.waitForTimeout(500);
	}
	throw new Error(`Save did not finish: ${(await dialogText(page)) || "no message"}`);
}

async function getDoc(page, doctype, name) {
	return call(page, "frappe.client.get", { doctype, name });
}

async function findName(page, doctype, filters) {
	const rows = await call(page, "frappe.client.get_list", { doctype, filters, fields: ["name"], limit_page_length: 5 });
	return rows.map((r) => r.name);
}

// Resume support: what this run already logged (a rerun never repeats a saved step).
function logged(file) {
	const full = path.join(RUN_DIR, file);
	return fs.existsSync(full)
		? fs.readFileSync(full, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line))
		: [];
}

function alreadySaved(tp, doctype) {
	return logged("ledger.jsonl").find((r) => r.test_id === tp.id && r.doctype === doctype && r.name);
}

function round(value, places) {
	const f = 10 ** places;
	return Math.round((Number(value) + Number.EPSILON) * f) / f;
}

test.beforeEach(async ({ page }) => {
	test.skip(!plan, "Set E2E_RUN_DIR to an evidence folder with plan.json.");
	await page.goto("/desk");
	await waitForDesk(page);
	await assertWritesAllowed(page, test);
});

test("00 Target Allocation: target, Chhatni %, multiple agents (read-only)", async ({ page }) => {
	const ta = plan.target_allocation_multi_agent;
	test.skip(!ta, "No Target Allocation with more than one agent on this site.");
	await page.goto(`/desk/target-allocation/${ta.name}`);
	await waitForDesk(page);
	await shot(page, "00-target-allocation");
	const doc = await getDoc(page, "Target Allocation", ta.name);
	check("00", "target_quantity", Number(ta.target_quantity), Number(doc.target_quantity));
	check("00", "assigned chhatni %", Number(ta.chhatni), Number(doc.chhatni));
	check("00", "agent rows (more than one agent per PPC)", Number(ta.agents), (doc.agent_details || []).length,
		(doc.agent_details || []).map((a) => a.agent_name).join(", "));
});

for (const tp of plan ? plan.tps : []) {
	test(`${tp.id} TP ${tp.tp_no} ${tp.party_name} (${tp.season}): ${tp.scenario}`, async ({ page }) => {
		let step = "start";
		try {
			if (tp.entry && alreadySaved(tp, "Entry")) {
				ledger(tp, "Entry (resume)", "Entry", alreadySaved(tp, "Entry").name, { status: "already saved earlier in this run; not repeated" });
			} else if (tp.entry) {
				step = "Entry";
				await openNewForm(page, "Entry");
				await setValues(page, {
					season: tp.season,
					ppc_name: tp.ppc_code,
					tp_no: tp.tp_no,
					agent_name: tp.entry.agent_name,
					entry_quantity: tp.entry.quantity,
					entry_price_per_quintal: tp.entry.price,
				});
				const entry = await save(page);
				const e = await getDoc(page, "Entry", entry);
				ledger(tp, step, "Entry", entry, { status: "saved", entry_quantity: e.entry_quantity, total_amount: e.total_amount });
				check(tp.id, "Entry linked to TP pass", tp.pass_unique_key, e.pass_unique_key);
				check(tp.id, "Entry total amount = qty x price", round(tp.entry.quantity * tp.entry.price, 2), round(e.total_amount, 2));
				await shot(page, `${tp.id}-entry`);
			}

			for (const [n, truck] of tp.trucks.entries()) {
				const label = `${tp.id}${String.fromCharCode(65 + n)}`;

				// Resume: a truck whose RST already exists is never repeated.
				if ((await findName(page, "RST Details", { name: truck.rst_no })).length) {
					const saved = await getDoc(page, "RST Details", truck.rst_no);
					const grns = saved.weigh_bridge_measurement
						? await findName(page, "GRN Note", { weigh_bridge_measurement: saved.weigh_bridge_measurement })
						: [];
					if (!grns.length) {
						throw new Error(`${label}: RST ${truck.rst_no} exists without a GRN (partial chain). Stopped for manual review; nothing repeated.`);
					}
					ledger(tp, `${label} (resume)`, "RST Details", truck.rst_no, { status: `already saved earlier in this run with ${grns.join(", ")}; not repeated` });
					continue;
				}

				step = `${label} Gate Entry`;
				await openNewForm(page, "Gate Entry");
				await setValues(page, {
					in_out: "In",
					in_purpose: "Paddy",
					going_to_weighment: 1,
					vehicle_no: truck.vehicle_no,
					driver_name: `${RUN} Driver`,
					party_name: tp.party_name,
					entry_datetime: await now(page),
				});
				const gateEntry = await save(page);
				ledger(tp, step, "Gate Entry", gateEntry, { status: "inside_mill", vehicle_no: truck.vehicle_no });

				step = `${label} Quality Check`;
				await openNewForm(page, "Quality Check");
				await setValues(page, {
					vehicle_no: truck.vehicle_no,
					gate_entry: gateEntry,
					qc_datetime: await now(page),
					driver_name: `${RUN} Driver`,
					paddy_quality: "Mota",
					staff_name: `${RUN} QC`,
					unloading_point: "Shed 1",
					paddy_received_in_pkt: truck.old_bags + truck.new_bags,
					paddy_returned: 0,
				});
				await setChildRow(page, "old_new_bags", { old_bags: truck.old_bags, new_bags: truck.new_bags });
				await setChildRow(page, "type_of_pkt", { jute_pkt_no: truck.jute_bags, no_of_plastic_bag: truck.plastic_bags });
				const qc = await save(page);
				const qcDecision = await docValue(page, "qc_decision");
				ledger(tp, step, "Quality Check", qc, {
					status: qcDecision,
					bags: `old ${truck.old_bags}, new ${truck.new_bags}, jute ${truck.jute_bags}, plastic ${truck.plastic_bags}`,
				});
				check(label, "QC decision with 0 returned bags", "Accepted", qcDecision);
				if (n === 0) await shot(page, `${label}-quality-check`);

				step = `${label} RST Details`;
				await openNewForm(page, "RST Details");
				await setValues(page, {
					rst_no: truck.rst_no,
					entry_datetime: tp.rst_datetime,
					vehicle_no: truck.vehicle_no,
					party_name: tp.party_name,
					tp_no: tp.tp_no,
					gross_vehicle_weight_qt: truck.load_qt,
					tare_vehicle_weight_qt: truck.tare_qt,
					gunny_weight_qt: truck.gunny_qt,
					deduction_qt: truck.deduction_qt,
					net_paddy_weight_qt: truck.expected_net_qt,
					commodity: "Paddy",
				});
				const rst = await save(page);
				const r = await getDoc(page, "RST Details", rst);
				ledger(tp, step, "RST Details", rst, { status: r.tp_status, season_code: r.season_code, rst_unique_key: r.rst_unique_key });
				check(label, "RST TP status", "TP Received", r.tp_status);
				check(label, "RST Season Code", tp.season_code, r.season_code);
				check(label, "RST Unique Key = canonical pass key", tp.pass_unique_key, r.rst_unique_key);
				if (n === 0) await shot(page, `${label}-rst`);

				step = `${label} Weigh Bridge (created by RST)`;
				const wbmName = r.weigh_bridge_measurement;
				if (!wbmName) throw new Error("RST saved but no Weigh Bridge Measurement was linked");
				const w = await getDoc(page, "Weigh Bridge Measurement", wbmName);
				ledger(tp, step, "Weigh Bridge Measurement", wbmName, {
					status: w.quality_test, load_qt: w.load_weight, tare_qt: w.tare_weight, gross_qt: w.gross_weight,
					gunny_qt: w.gunny_weight, deduction_qt: w.deduction, net_qt: w.net_weight, gunny_type: w.gunny_type,
				});
				check(label, "WBM gross = load - tare", round(truck.load_qt - truck.tare_qt, 3), round(w.gross_weight, 3));
				check(label, "WBM net = gross - gunny - deduction", truck.expected_net_qt, round(w.net_weight, 3),
					`${w.load_weight} - ${w.tare_weight} - ${w.gunny_weight} - ${w.deduction}`);
				check(label, "WBM gunny type", truck.gunny_qt > 0 ? "Gunny Cut" : "Gunny Gross", w.gunny_type);
				check(label, "No GRN before Gate Exit", 0, (await findName(page, "GRN Note", { weigh_bridge_measurement: wbmName })).length);

				step = `${label} Gate Exit`;
				await openNewForm(page, "Gate Exit");
				await setValues(page, {
					out_purpose: "Others",
					out_purpose_detail: `${RUN} ${label} unloading complete`,
					vehicle_no: truck.vehicle_no,
					gate_entry_in: gateEntry,
					exit_datetime: await now(page),
				});
				const gateExit = await save(page);
				ledger(tp, step, "Gate Exit", gateExit, { status: "exited", vehicle_no: truck.vehicle_no });

				step = `${label} GRN (auto after Gate Exit)`;
				let grns = [];
				for (let i = 0; i < 20 && !grns.length; i++) {
					grns = await findName(page, "GRN Note", { weigh_bridge_measurement: wbmName });
					if (!grns.length) await page.waitForTimeout(500);
				}
				check(label, "Exactly one GRN created after Gate Exit", 1, grns.length);
				for (const grnName of grns) {
					const g = await getDoc(page, "GRN Note", grnName);
					ledger(tp, step, "GRN Note", grnName, {
						status: g.tp_fulfillment_status, net_qt: g.net_weight, gate_exit: g.gate_exit, chhatni_assigned: g.chhatni,
					});
					check(label, "GRN net = WBM net", round(w.net_weight, 3), round(g.net_weight, 3));
					check(label, "GRN Gate Exit link", gateExit, g.gate_exit);
					check(label, "GRN pass key", tp.pass_unique_key, g.pass_unique_key);
					if (n === 0) {
						await page.goto(`/desk/grn-note/${encodeURIComponent(grnName)}`);
						await waitForDesk(page);
						await shot(page, `${label}-grn`);
					}
				}
			}

			const dupDone = logged("checks.jsonl").some((c) => c.test_id === tp.id && c.check.startsWith("Duplicate GRN rejected"));
			if (tp.duplicate_grn_check && !dupDone) {
				step = "Duplicate GRN attempt";
				const truck = tp.trucks[0];
				const before = await findName(page, "GRN Note", { rst_no: truck.rst_no });
				// Standard API insert (same server validations as the form), with the pass filled in first as in
				// manual entry. A form save hung the browser in two runs, so this step has a time limit.
				let rejected = "";
				try {
					const dup = await Promise.race([
						call(page, "frappe.client.insert", {
							doc: { doctype: "GRN Note", pass_unique_key: tp.pass_unique_key, rst_no: truck.rst_no, receipt_datetime: await now(page) },
						}),
						new Promise((_, reject) => setTimeout(() => reject(new Error("no response within 60 s")), 60_000)),
					]);
					ledger(tp, step, "GRN Note", dup.name, { status: "UNEXPECTEDLY SAVED (duplicate)" });
				} catch (error) {
					rejected = String(error.message);
				}
				await closeDialogs(page);
				const after = await findName(page, "GRN Note", { rst_no: truck.rst_no });
				check(tp.id, "Duplicate GRN rejected (count unchanged)", before.length, after.length, rejected.slice(0, 200));
			}

			if (tp.chhatni_rate !== null && alreadySaved(tp, "Chhatni")) {
				ledger(tp, "Chhatni (resume)", "Chhatni", alreadySaved(tp, "Chhatni").name, { status: "already saved earlier in this run; not repeated" });
			} else if (tp.chhatni_rate !== null) {
				step = "Chhatni";
				await openNewForm(page, "Chhatni");
				await setValues(page, { season: tp.season, ppc_name: tp.ppc_code, tp_no: tp.tp_no, chhatni_kg_per_qtl: tp.chhatni_rate });
				const chhatni = await save(page);
				const c = await getDoc(page, "Chhatni", chhatni);
				ledger(tp, step, "Chhatni", chhatni, {
					status: "saved", rate_kg_per_qtl: c.chhatni_kg_per_qtl, net_qt: c.net_weight, chhatni_kg: c.chhatni_kg,
					chhatni_qt: c.chhatni_qt, received_pct: c.received_chhatni_pct,
				});
				const net = round(tp.trucks.reduce((s, t) => s + t.expected_net_qt, 0), 3);
				const kg = round(net * tp.chhatni_rate, 3);
				const qt = round(kg / 100, 3);
				check(tp.id, "Chhatni net weight = total WBM net of the pass", net, round(c.net_weight, 3));
				check(tp.id, "Chhatni KG = net x rate", kg, round(c.chhatni_kg, 3));
				check(tp.id, "Chhatni QT = KG / 100", qt, round(c.chhatni_qt, 3));
				check(tp.id, "Received Chhatni % = QT / TP qty x 100", round((qt / tp.tp_quantity) * 100, 2), round(c.received_chhatni_pct, 2));
				await shot(page, `${tp.id}-chhatni`);
			}
		} catch (error) {
			const message = String(error.message || error).slice(0, 500);
			ledger(tp, step, "", "", { status: `FAILED at ${step}`, error: message });
			await shot(page, `${tp.id}-FAILED`).catch(() => {});
			throw error;
		}
	});
}

test("RS RST status cases (saved)", async ({ page }) => {
	for (const c of plan ? plan.rst_status_cases : []) {
		try {
			await openNewForm(page, "RST Details");
			await setValues(page, { rst_no: c.rst_no, entry_datetime: c.rst_datetime, vehicle_no: c.vehicle_no, party_name: c.party_name, tp_no: c.tp_no });
			const rst = await save(page);
			const r = await getDoc(page, "RST Details", rst);
			ledger(null, `RST status ${c.id}`, "RST Details", rst, {
				status: r.tp_status, party_name: c.party_name, tp_no: c.tp_no, weigh_bridge_measurement: r.weigh_bridge_measurement || "",
			});
			if (r.weigh_bridge_measurement) {
				ledger(null, `RST status ${c.id} (Weigh Bridge created by RST)`, "Weigh Bridge Measurement", r.weigh_bridge_measurement, {
					status: "created without TP (awaiting TP No)",
				});
			}
			check(c.id, `RST status: ${c.expected}`, c.expected, r.tp_status);
			await shot(page, `${c.id}-rst-${c.expected.replace(/ /g, "-")}`);
		} catch (error) {
			ledger(null, `RST status ${c.id}`, "RST Details", "", { status: "FAILED", error: String(error.message).slice(0, 500) });
			check(c.id, `RST status: ${c.expected}`, c.expected, `save failed: ${String(error.message).slice(0, 120)}`);
		}
	}
});

test("RP Report screenshots", async ({ page }) => {
	for (const report of ["Mandi Book", "Abstract Report", "Abstract Physical", "Entry Report"]) {
		await page.goto(`/desk/query-report/${encodeURIComponent(report)}`);
		await waitForDesk(page);
		await page.waitForTimeout(3000);
		await shot(page, `report-${report.replace(/ /g, "-")}`);
	}
});
