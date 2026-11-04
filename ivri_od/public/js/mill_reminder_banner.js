// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Monthly reminders (Mill Reminder) as a banner at the top of the Desktop page (the page of app icons that opens at /desk), for example the electricity
// bill and the EPF. It shows on that page only: not on workspaces, forms, lists or reports.
// The server says which reminders this user should see today (by day of month and role). "Mark as completed" opens a form (Date and Time filled in,
// Bank, Amount, Entered By, Approved By); when it is submitted the reminder is hidden for everybody until next month. See ivri_od/procurement/mill_reminder.py.
// A luxury look: a floating midnight-blue panel with a fine champagne-gold edge that rises in, with a picture of Kanha in a gold ring, the message travelling from the
// right end of the screen to the left end again and again, fading in and out at the ends (it stops while the mouse is on it), and a gold pill button.
// Motion is switched off for users who ask their system for reduced motion.
(function () {
	if (typeof window === "undefined" || window.__ivri_od_reminder_banner) return;
	window.__ivri_od_reminder_banner = true;

	const GET = "ivri_od.procurement.mill_reminder.get_active_reminders";
	const DONE = "ivri_od.procurement.mill_reminder.mark_completed";
	const PEOPLE = "ivri_od.procurement.mill_reminder.get_people";
	const BANKS = "ivri_od.procurement.mill_reminder.get_banks";
	const BOX = "ivri-od-reminder-banner";
	const PAGE = "page-desktop"; // the element of the Desktop page (the app icons), where the banner is placed
	const REFRESH_EVERY = 10 * 60 * 1000; // ten minutes

	const ICON = "/assets/ivri_od/images/reminder_kanha.jpg?v=1"; // Kanha playing the flute; replace the file to use another picture (see reminder_kanha_CREDITS.txt)
	const SPEED = 110; // pixels per second: the text takes (screen width + text width) / SPEED seconds to cross the screen

	function add_style() {
		if (document.getElementById("ivri-od-reminder-style")) return;
		const style = document.createElement("style");
		style.id = "ivri-od-reminder-style";
		style.textContent = `
			/* Midnight and champagne gold: a floating dark panel with a fine gold edge, soft light and a message that fades in and out at the ends */
			#${BOX} { position: relative; margin: 8px 14px; border-radius: 14px; overflow: hidden; color: #f3e3b3; font-family: inherit;
				background: radial-gradient(120% 220% at 0% 50%, #1a2a5e 0%, #0e1838 45%, #080d22 100%);
				border: 1px solid rgba(214, 178, 100, 0.55);
				box-shadow: 0 12px 32px rgba(6, 10, 28, 0.35), 0 2px 6px rgba(6, 10, 28, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.07);
				animation: ivri-rise 0.7s cubic-bezier(0.2, 0.8, 0.2, 1); }
			#${BOX}::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 1px; z-index: 3;
				background: linear-gradient(90deg, transparent, #f1d896 30%, #fff6d8 50%, #f1d896 70%, transparent); background-size: 200% 100%; animation: ivri-edge 5s linear infinite; }
			#${BOX}::after { content: ""; position: absolute; top: 0; bottom: 0; width: 160px; left: -200px; z-index: 1; pointer-events: none;
				background: linear-gradient(100deg, transparent, rgba(255, 244, 206, 0.09), transparent); animation: ivri-sweep 7s ease-in-out infinite; }
			#${BOX} .ivri-reminder-row { position: relative; display: flex; align-items: center; min-height: 72px; padding: 8px 16px 8px 14px; }
			#${BOX} .ivri-reminder-row + .ivri-reminder-row { border-top: 1px solid rgba(214, 178, 100, 0.25); }
			#${BOX} .ivri-reminder-left { position: relative; z-index: 2; display: flex; align-items: center; gap: 14px; flex: none; padding-right: 22px; margin-right: 6px;
				border-right: 1px solid rgba(214, 178, 100, 0.3); }
			#${BOX} .ivri-reminder-icon { width: 54px; height: 54px; border-radius: 50%; object-fit: cover; flex: none; padding: 2px;
				background: linear-gradient(135deg, #fff1c4, #c9a25a 50%, #f3dc9e); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 241, 196, 0.35);
				animation: ivri-breathe 4s ease-in-out infinite; }
			#${BOX} .ivri-reminder-actions { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; }
			#${BOX} .ivri-reminder-label { font-size: 10px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: #d6b264; line-height: 1; }
			#${BOX} .ivri-reminder-lane { position: relative; z-index: 2; flex: 1; min-width: 0; overflow: hidden; white-space: nowrap;
				-webkit-mask-image: linear-gradient(90deg, transparent 0, #000 7%, #000 93%, transparent 100%); mask-image: linear-gradient(90deg, transparent 0, #000 7%, #000 93%, transparent 100%); }
			#${BOX} .ivri-reminder-text { display: inline-block; padding-left: 100%; font-size: 17px; font-weight: 600; letter-spacing: 0.7px; color: #f6e8bf;
				text-shadow: 0 1px 12px rgba(214, 178, 100, 0.45); animation: ivri-ticker var(--ivri-duration, 16s) linear infinite; }
			#${BOX} .ivri-reminder-text::after { content: "  ◆"; color: #d6b264; font-size: 11px; vertical-align: middle; }
			#${BOX} .ivri-reminder-lane:hover .ivri-reminder-text { animation-play-state: paused; }
			#${BOX} .btn { flex: none; padding: 3px 14px; font-size: 12px; font-weight: 700; letter-spacing: 0.6px; color: #12182f; border: 0; border-radius: 999px;
				background: linear-gradient(135deg, #fff1c4, #d6b264 55%, #f0d78f); box-shadow: 0 4px 12px rgba(214, 178, 100, 0.35); transition: transform 0.15s ease, box-shadow 0.15s ease; }
			#${BOX} .btn:hover { transform: translateY(-1px); box-shadow: 0 7px 18px rgba(214, 178, 100, 0.55); color: #12182f; }
			@keyframes ivri-rise { from { transform: translateY(-14px) scale(0.985); opacity: 0; } to { transform: translateY(0) scale(1); opacity: 1; } }
			@keyframes ivri-edge { from { background-position: 0 0; } to { background-position: 200% 0; } }
			@keyframes ivri-sweep { 0% { left: -200px; } 55%, 100% { left: 110%; } }
			@keyframes ivri-breathe { 0%, 100% { box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 241, 196, 0.35); } 50% { box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45), 0 0 18px 3px rgba(240, 215, 143, 0.55); } }
			@keyframes ivri-ticker { from { transform: translateX(0); } to { transform: translateX(-100%); } }
			@media (prefers-reduced-motion: reduce) {
				#${BOX}, #${BOX}::before, #${BOX}::after, #${BOX} .ivri-reminder-icon { animation: none !important; }
				#${BOX} .ivri-reminder-text { animation: none !important; padding-left: 0; white-space: normal; }
				#${BOX} .ivri-reminder-lane { white-space: normal; padding: 6px 12px; -webkit-mask-image: none; mask-image: none; }
			}`;
		document.head.appendChild(style);
	}

	// "Mark as completed" asks for the payment details first: Date and Time (filled in), Bank, Amount, Entered By and Approved By; Submit saves them.
	function ask_details(reminder) {
		frappe.call({
			method: BANKS,
			callback(banks_result) {
				const banks = banks_result.message || [];
				frappe.call({
					method: PEOPLE,
					callback(r) {
						open_form(reminder, r.message || [], banks);
					},
				});
			},
		});
	}

	function open_form(reminder, people, banks) {
		const label = (p) => `${p.full_name || p.user} (${p.user})`;
		const options = ["", ...people.map(label)];
		const user_of = (text) => (people.find((p) => label(p) === text) || {}).user;
		const me = `${frappe.session.user_fullname || frappe.session.user} (${frappe.session.user})`; // Entered By: the person who is logged in, locked
		const dialog = new frappe.ui.Dialog({
			title: __("Mark as completed"),
			fields: [
				{ fieldname: "message", fieldtype: "HTML", options: `<div style="font-weight:600;margin-bottom:6px">${frappe.utils.escape_html(reminder.message)}</div>` },
				{ label: __("Date and Time"), fieldname: "completed_on", fieldtype: "Datetime", read_only: 1, default: frappe.datetime.now_datetime() },
				{ label: __("Bank"), fieldname: "bank", fieldtype: "Autocomplete", options: banks, reqd: 1, description: __("Start typing the name of the bank, then choose it from the list.") },
				{ label: __("Amount"), fieldname: "amount", fieldtype: "Currency", reqd: 1 },
				{ label: __("Entered By"), fieldname: "entered_by", fieldtype: "Data", read_only: 1, default: me, description: __("The person logged in. It cannot be changed.") },
				{ label: __("Approved By"), fieldname: "approved_by", fieldtype: "Select", options: options, reqd: 1 },
			],
			primary_action_label: __("Submit"),
			primary_action(values) {
				if (!banks.includes(values.bank)) return frappe.msgprint(__("Choose the bank from the list."));
				if (!(flt(values.amount) > 0)) return frappe.msgprint(__("Amount must be more than 0."));
				frappe.call({
					method: DONE,
					args: {
						reminder: reminder.name,
						period: reminder.period,
						bank: values.bank,
						amount: values.amount,
						entered_by: frappe.session.user, // the server uses the person logged in whatever is sent
						approved_by: user_of(values.approved_by),
					},
					freeze: true,
					freeze_message: __("Submitting ..."),
					callback(res) {
						if (res.exc) return;
						dialog.hide();
						frappe.show_alert({ message: __("Submitted. The reminder is completed."), indicator: "green" });
						load();
					},
				});
			},
		});
		dialog.show();
	}

	function render(reminders) {
		$("#" + BOX).remove();
		if (!reminders || !reminders.length) return;
		add_style();
		const box = $(`<div id="${BOX}" role="alert" aria-live="polite"></div>`);
		reminders.forEach((reminder) => {
			const row = $(`<div class="ivri-reminder-row">
				<div class="ivri-reminder-left">
					<img class="ivri-reminder-icon" src="${ICON}" alt="Kanha">
					<div class="ivri-reminder-actions">
						<span class="ivri-reminder-label">${__("Reminder")}</span>
						<button class="btn btn-sm">${__("Mark as completed")}</button>
					</div>
				</div>
				<div class="ivri-reminder-lane"><span class="ivri-reminder-text">${frappe.utils.escape_html(reminder.message)}</span></div>
			</div>`);
			row.find("button").on("click", function () {
				ask_details(reminder);
			});
			box.append(row);
		});
		// the banner sits at the top of the Desktop page only, inside that page, so it never shows on workspaces, forms, lists or reports
		$("#" + PAGE).prepend(box);
		// the message starts at the right end of the screen and travels to the left end, then starts again; the speed is the same on every screen
		box.find(".ivri-reminder-lane").each(function () {
			const lane = this;
			const text = lane.querySelector(".ivri-reminder-text");
			requestAnimationFrame(() => {
				const distance = text.offsetWidth; // the text has a full lane of padding before it, so this is the lane plus the text
				text.style.setProperty("--ivri-duration", Math.max(distance / SPEED, 8) + "s");
			});
		});
	}

	// The banner shows on one page only: the Desktop (the page of app icons that opens at /desk). It is placed inside that page, so it is on no other
	// page: not a workspace, a form, a list or a report.
	function on_desktop_page() {
		return $("#" + PAGE).is(":visible");
	}

	function load() {
		try {
			if (!frappe.session || frappe.session.user === "Guest") return;
			if (!on_desktop_page()) return $("#" + BOX).remove();
			frappe.call({ method: GET, type: "GET", silent: true, callback: (r) => render(r.message) });
		} catch (e) {
			// the desk is not ready yet: the next page change or refresh tries again
		}
	}

	$(function () {
		setTimeout(load, 1500);
		$(document).on("page-change", () => setTimeout(load, 100));
		if (frappe.router && frappe.router.on) frappe.router.on("change", () => setTimeout(load, 100));
		setInterval(load, REFRESH_EVERY);
	});
})();
