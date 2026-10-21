// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Flow: Connect Session → agent opens Chrome → user logs in, opens any page
// from the portal menu, sets filters, clicks Search → agent scrapes the table
// → this form pulls the rows and receipts and saves them as Portal Record,
// under the section named from the page (one "run" per Search).

const PORTAL_AGENT = "http://127.0.0.1:8765";
const PORTAL_AGENT_PROTOCOL = "ppasagent://start";
const PORTAL_METHOD = "ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction";
const PORTAL_POLL_MS = 2000;
// Oldest agent whose portal data is right (see "portal_version" in ppas_agent.py /health).
const PORTAL_AGENT_MIN_VERSION = 19;
const PORTAL_PAGE_SIZE = 50;
const PORTAL_BATCH_PLAIN = 25;
const PORTAL_BATCH_WITH_RECEIPTS = 5;

// Live agent sessions, keyed by document name. Lives only while the desk tab is open.
const portal_sessions = {};

frappe.ui.form.on("Portal Data Extraction", {
	setup(frm) {
		frm.set_query("site", () => ({ filters: { enabled: 1 } }));
		// Each mill has its own portal account: pick the mill before Connect Session.
		frm.set_query("mill", () => ({ filters: { is_active: 1 } }));
	},

	rows_to_save(frm) {
		// Saved at once: each Search reads it, and the form reloads after a Search.
		if (!frm.is_new()) {
			frm.save();
		}
		// The open agent session stops paging at the new limit from the next Search.
		const session = portal_sessions[frm.doc.name];
		if (session) {
			agent_fetch("/portal/settings", {
				method: "POST",
				token: session.token,
				body: { row_limit: PORTAL_ROW_LIMITS[frm.doc.rows_to_save] || 0 },
			}).catch(() => {});
		}
	},

	refresh(frm) {
		add_portal_buttons(frm);
		const session = portal_sessions[frm.doc.name];
		// The rows of an open session are saved under this mill: not changed until it is closed.
		frm.set_df_property("mill", "read_only", session ? 1 : 0);
		if (session) {
			show_portal_message(frm, session.last_message || "", session.last_color || "blue", true);
			start_polling(frm);
		}
	},
});

function add_portal_buttons(frm) {
	if (!frm.doc.site) {
		return;
	}
	const session = portal_sessions[frm.doc.name];

	frm.add_custom_button(session ? __("Reconnect Session") : __("Connect Session"), () =>
		connect_session(frm)
	).addClass("btn-primary");

	// No "Extract Now": the agent reads the table by itself when Search is clicked.
	if (session) {
		frm.add_custom_button(session.closing ? __("Closing...") : __("Close Session"), () => close_session(frm));
	}
	if (!frm.is_new()) {
		frm.add_custom_button(__("Open Records"), () =>
			frappe.set_route("List", "Portal Record", { site: frm.doc.site, mill_id: frm.doc.mill })
		);
	}
}

// ---------------------------------------------------------------
// Agent calls
// ---------------------------------------------------------------

async function agent_fetch(path, { method = "GET", token = null, body = null } = {}) {
	const headers = { "Content-Type": "application/json" };
	if (token) {
		headers["X-Portal-Token"] = token;
	}
	const response = await fetch(`${PORTAL_AGENT}${path}`, {
		method,
		headers,
		cache: "no-store",
		body: body ? JSON.stringify(body) : null,
	});
	let data = {};
	try {
		data = await response.json();
	} catch (e) {
		data = {};
	}
	if (!response.ok || data.success === false) {
		throw new Error(data.error || data.message || __("Agent request failed ({0})", [response.status]));
	}
	return data;
}

async function agent_health() {
	try {
		return await agent_fetch("/health");
	} catch (e) {
		return null;
	}
}

async function ensure_portal_agent(frm) {
	let health = await agent_health();
	if (!health) {
		show_portal_message(frm, __("Starting the local agent. Allow the launcher if Windows asks."), "orange");
		const link = document.createElement("a");
		link.href = PORTAL_AGENT_PROTOCOL;
		link.style.display = "none";
		document.body.appendChild(link);
		link.click();
		link.remove();
		for (let i = 0; i < 20 && !health; i++) {
			await sleep(1000);
			health = await agent_health();
		}
	}
	if (!health) {
		throw new Error(__("The local agent is not running. Please install the agent on this computer."));
	}
	if (health.portal && (health.portal_version || 1) < PORTAL_AGENT_MIN_VERSION) {
		throw new Error(
			__(
				"The installed agent is an old version (it cannot skip rows already in the ERP). Please close it and install the latest agent."
			)
		);
	}
	if (!health.portal) {
		throw new Error(
			__("The installed agent is an old version without portal support. Please install the latest agent.")
		);
	}
}

// ---------------------------------------------------------------
// Session
// ---------------------------------------------------------------

async function connect_session(frm) {
	if (!frm.doc.mill) {
		frappe.msgprint({
			title: __("Connect Session"),
			message: __("Select the Mill No. whose portal account you will log in with."),
			indicator: "orange",
		});
		frm.scroll_to_field("mill");
		return;
	}
	if (frm.is_new() || frm.is_dirty()) {
		await frm.save();
	}
	try {
		await ensure_portal_agent(frm);
		const config = await frappe.xcall(`${PORTAL_METHOD}.get_session_config`, { name: frm.doc.name });
		const started = await agent_fetch("/portal/start", { method: "POST", body: config });

		portal_sessions[frm.doc.name] = {
			token: started.token,
			last_result_id: "",
			importing: false,
			timer: null,
		};
		await frappe.xcall(`${PORTAL_METHOD}.mark_connected`, { name: frm.doc.name });
		await frm.reload_doc();
		show_portal_message(
			frm,
			__("Chrome opened. Log in with the account of mill {0}, open a page from the portal menu, set filters and click Search.", [
				frm.doc.mill,
			]),
			"blue"
		);
		start_polling(frm);
	} catch (e) {
		show_portal_message(frm, e.message, "red");
		frappe.msgprint({ title: __("Connect Session"), message: e.message, indicator: "red" });
	}
}

// Close Session keeps everything read so far: a read in progress is stopped
// and its rows saved (see poll_agent), then the agent session is closed.
async function close_session(frm) {
	const session = portal_sessions[frm.doc.name];
	if (!session || session.closing) {
		return;
	}
	session.closing = true;
	frm.refresh();
	try {
		const status = await agent_fetch("/portal/status", { token: session.token });
		if (status.state === "extracting") {
			await agent_fetch("/portal/finish", { method: "POST", token: session.token });
		}
	} catch (e) {
		// Agent already gone: nothing more to save from it.
		await finish_close(frm);
		return;
	}
	show_portal_message(frm, __("Saving the rows read so far, then closing the session..."), "orange", true);
	start_polling(frm);
}

// ``saved_message``: a summary kept on the form instead of being cleared.
async function finish_close(frm, saved_message = "", saved_color = "green") {
	const session = portal_sessions[frm.doc.name];
	if (!session) {
		return;
	}
	stop_polling(frm.doc.name);
	try {
		await agent_fetch("/portal/close", { method: "POST", token: session.token });
	} catch (e) {
		// Agent may already be gone; nothing to clean up on our side.
	}
	delete portal_sessions[frm.doc.name];
	frm.dashboard.clear_headline();
	frm.refresh();
	if (saved_message) {
		show_portal_message(frm, saved_message, saved_color, true);
	}
	frappe.show_alert({ message: __("Session closed and Chrome closed. All rows read were saved."), indicator: "green" });
}

function start_polling(frm) {
	const name = frm.doc.name;
	const session = portal_sessions[name];
	if (!session || session.timer) {
		return;
	}
	session.timer = setInterval(() => poll_agent(frm, name), PORTAL_POLL_MS);
}

function stop_polling(name) {
	const session = portal_sessions[name];
	if (session && session.timer) {
		clearInterval(session.timer);
		session.timer = null;
	}
}

async function poll_agent(frm, name) {
	const session = portal_sessions[name];
	// Stop when the user has moved to another document.
	if (!session || frm.doc.name !== name || cur_frm !== frm) {
		stop_polling(name);
		return;
	}
	if (session.importing) {
		return;
	}

	let status;
	try {
		status = await agent_fetch("/portal/status", { token: session.token });
	} catch (e) {
		stop_polling(name);
		delete portal_sessions[name];
		show_portal_message(frm, __("Lost contact with the agent: {0}", [e.message]), "red");
		frm.refresh();
		return;
	}

	const colors = { ready: "green", error: "red", closed: "red", extracting: "orange" };
	if (!session.closing) {
		show_portal_message(frm, status.message, colors[status.state] || "blue");
	}

	if (status.state === "closed") {
		stop_polling(name);
		delete portal_sessions[name];
		frm.refresh();
		return;
	}
	// One Search can give several results (one per table, e.g. WINGS e_tec): save each, in order.
	session.imported = session.imported || [];
	const ids = status.result_ids || (status.result_id ? [status.result_id] : []);
	const fresh = ids.filter((id) => !session.imported.includes(id));
	for (const result_id of fresh) {
		session.imported.push(result_id);
		session.last_result_id = result_id;
		const saved = await import_result(frm, session, { ...status, result_id });
		// Tell the user in the portal's Chrome too; the session stays open for the next page.
		await notify_chrome(
			session,
			saved
				? __("{0} You can open another page and Search again.", [saved.text])
				: __("Not saved in ERP; see the Portal Data Extraction form."),
			saved ? (saved.failed ? "orange" : "green") : "red"
		);
	}
	// Close Session waits until the read is stopped and its rows are saved.
	if (session.closing && status.state !== "extracting" && ids.every((id) => session.imported.includes(id))) {
		await finish_close(frm);
	}
}

async function notify_chrome(session, message, color) {
	try {
		await agent_fetch("/portal/notify", { method: "POST", token: session.token, body: { message, color } });
	} catch (e) {
		// Only a courtesy message: the form already shows the result.
	}
}

// ---------------------------------------------------------------
// Import
// ---------------------------------------------------------------

// Saves one result; returns {text, failed} for the closing message, or null when it failed.
async function import_result(frm, session, status) {
	session.importing = true;
	const name = frm.doc.name;
	let run = null;
	let section = "";
	try {
		// All rows of this Search, then the ones "Rows to Save" keeps (e.g. Last 5 to test a page).
		let page = await agent_fetch(
			`/portal/result?result_id=${encodeURIComponent(status.result_id)}&offset=0&limit=${PORTAL_PAGE_SIZE}`,
			{ token: session.token }
		);
		const first = page;
		let all = page.rows.map((row, i) => ({ index: i, row }));
		while (page.rows.length && all.length < page.total) {
			page = await agent_fetch(
				`/portal/result?result_id=${encodeURIComponent(status.result_id)}&offset=${all.length}&limit=${PORTAL_PAGE_SIZE}`,
				{ token: session.token }
			);
			all = all.concat(page.rows.map((row, i) => ({ index: page.offset + i, row })));
		}
		const picked = pick_rows_to_save(all, first.columns, frm.doc.rows_to_save);

		const started = await frappe.xcall(`${PORTAL_METHOD}.begin_run`, {
			name,
			total_rows: first.total,
			pages: first.pages,
			columns: first.columns,
			page_url: first.page_url,
			page_heading: first.page_heading,
			page_title: first.page_title,
			table_id: first.table_id || "",
			table_title: first.table_title || "",
			active_tab: first.active_tab || "",
			table_ids: first.table_ids || "",
			mill_id: first.mill_id || status.mill_id || "",
			page_filters: first.page_filters || [],
			rows_kept: picked.rows.length,
			kept_note: picked.note,
		});
		run = started.run;
		section = started.section;

		const totals = { inserted: 0, updated: 0, unchanged: 0, failed: 0, receipts: 0 };
		const batch_size = picked.rows.some(
			(e) => e.row.has_receipt || (e.row.documents || []).length || (e.row.details || []).length > 20
		)
			? PORTAL_BATCH_WITH_RECEIPTS
			: PORTAL_BATCH_PLAIN;
		let done = 0;
		for (let i = 0; i < picked.rows.length; i += batch_size) {
			const rows = [];
			for (const entry of picked.rows.slice(i, i + batch_size)) {
				rows.push(await build_import_row(session, status.result_id, entry.index, entry.row));
			}
			const result = await frappe.xcall(`${PORTAL_METHOD}.import_rows`, { name, run, rows });
			Object.keys(totals).forEach((k) => (totals[k] += result[k] || 0));
			done += rows.length;
			show_portal_message(
				frm,
				__("Saving '{0}' to ERP: {1} of {2} rows...", [section, done, picked.rows.length]),
				"orange"
			);
		}

		await frappe.xcall(`${PORTAL_METHOD}.finish_run`, { name, run, status: "Completed" });
		await frm.reload_doc();
		const text = __("'{0}' saved: {1} new, {2} updated, {3} unchanged, {4} errors.", [
			section,
			totals.inserted,
			totals.updated,
			totals.unchanged,
			totals.failed,
		]);
		show_portal_message(frm, text, totals.failed ? "orange" : "green");
		return { text, failed: totals.failed > 0 };
	} catch (e) {
		try {
			if (run) {
				await frappe.xcall(`${PORTAL_METHOD}.finish_run`, {
					name,
					run,
					status: "Failed",
					message: e.message,
				});
				await frm.reload_doc();
			}
		} catch (ignore) {
			// The error below already tells the user what went wrong.
		}
		show_portal_message(frm, __("Extraction failed: {0}", [e.message]), "red");
	} finally {
		session.importing = false;
	}
}

// "Rows to Save": All, Latest Entry, Last 5/10/20. The newest rows by the
// table's date column (a column where most cells are dd/mm/yyyy or dd-mm-yyyy),
// else the first rows as shown on the portal. Kept in portal order.
// Same list as ROW_LIMITS in portal_data_extraction.py.
const PORTAL_ROW_LIMITS = { "Latest Entry": 1, "Last 5": 5, "Last 10": 10, "Last 20": 20 };
const PORTAL_DATE = /^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})/;

function pick_rows_to_save(entries, columns, choice) {
	const limit = PORTAL_ROW_LIMITS[choice];
	if (!limit || entries.length <= limit) {
		return { rows: entries, note: "" };
	}
	const date_of = (entry, column) => {
		const m = PORTAL_DATE.exec(String((entry.row.cells || {})[column] || "").trim());
		return m ? Number(m[3]) * 10000 + Number(m[2]) * 100 + Number(m[1]) : null;
	};
	const date_column = (columns || []).find(
		(c) => entries.filter((e) => date_of(e, c) !== null).length >= entries.length * 0.8
	);
	let chosen;
	if (date_column) {
		chosen = entries
			.slice()
			.sort((a, b) => (date_of(b, date_column) || 0) - (date_of(a, date_column) || 0) || b.index - a.index)
			.slice(0, limit)
			.sort((a, b) => a.index - b.index);
	} else {
		chosen = entries.slice(0, limit);
	}
	return {
		rows: chosen,
		note: date_column
			? __("newest by '{0}'", [date_column])
			: __("first rows as shown on the portal: no date column"),
	};
}

async function build_import_row(session, result_id, row_index, row) {
	const out = {
		cells: row.cells,
		// Position on the portal (rows already in the ERP are not sent), keeps reports in portal order.
		row_no: row.position || row_index + 1,
		row_sig: row.row_sig || "",
		receipt_error: row.receipt_error || "",
		detail_error: row.detail_error || "",
	};
	if (row.details) {
		out.details = row.details;
		out.details_footer = row.details_footer || [];
	}
	// Several documents per row (e.g. DCRO DC Transit Challan: Details, AC Note Doc).
	if ((row.documents || []).length) {
		out.documents = [];
		for (let n = 0; n < row.documents.length; n++) {
			const doc = row.documents[n];
			if (!doc.has_file) {
				out.documents.push({ label: doc.label, error: doc.error || __("not saved") });
				continue;
			}
			try {
				const file = await agent_fetch(
					`/portal/receipt?result_id=${encodeURIComponent(result_id)}&row=${row_index}&doc=${n}`,
					{ token: session.token }
				);
				out.documents.push({ label: doc.label, ...file });
			} catch (e) {
				out.documents.push({ label: doc.label, error: e.message });
			}
		}
	}
	if (!row.has_receipt) {
		return out;
	}
	try {
		const receipt = await agent_fetch(
			`/portal/receipt?result_id=${encodeURIComponent(result_id)}&row=${row_index}`,
			{ token: session.token }
		);
		out.receipt = {
			filename: receipt.filename,
			content_b64: receipt.content_b64,
			source_url: receipt.source_url,
		};
	} catch (e) {
		out.receipt_error = e.message;
	}
	return out;
}

// ---------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------

function show_portal_message(frm, message, color, force = false) {
	const session = portal_sessions[frm.doc.name];
	if (!force && session && session.last_message === message && session.last_color === color && message) {
		return; // same status as the last poll: nothing to redraw
	}
	if (session) {
		session.last_message = message;
		session.last_color = color;
	}
	if (message) {
		frm.dashboard.set_headline_alert(frappe.utils.escape_html(message), color);
	}
}

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
