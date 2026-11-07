// Procurement sidebar header: show the Shyamji "S" emblem instead of the grey first-letter icon.
// Frappe's SidebarHeader skips hidden Desktop Icons, and "Procurement" is a hidden one, so it falls back
// to the generic letter icon and never reads an icon file. Only this one sidebar is changed.
// The same sidebar also shows "Govt. Procurement & CMR" as its name (top-left header and the Workspaces switcher).
// Frappe uses "Procurement" as the internal key and URL of this desk, so only the shown text is replaced.
(function () {
	const SIDEBAR_TITLE = "Procurement";
	const DISPLAY_TITLE = "Govt. Procurement & CMR";
	const LOGO_URL = "/assets/ivri_od/icons/desktop_icons/solid/procurement.svg";

	function patch_sidebar_header() {
		const header = frappe.ui && frappe.ui.SidebarHeader;
		if (!header) return false;
		if (header.prototype.__ivri_od_logo) return true;

		const set_header_icon = header.prototype.set_header_icon;
		header.prototype.set_header_icon = function () {
			set_header_icon.apply(this, arguments);
			if (this.sidebar && this.sidebar.sidebar_title === SIDEBAR_TITLE) {
				this.header_icon = `<img src="${LOGO_URL}" alt="">`;
			}
		};

		// The longer name does not fit on one line in the header: let it wrap (Procurement sidebar only).
		// Frappe fixes the header at 48px and clips the title box, so the second line was cut off:
		// let the header grow with the text, and stop clipping.
		const header_css = `.body-sidebar[data-title="${SIDEBAR_TITLE}"] .sidebar-header`;
		const style = document.createElement("style");
		style.textContent = `
			${header_css} { height: auto; min-height: 48px; padding: 8px; }
			${header_css} .sidebar-item-icon { flex-shrink: 0; }
			${header_css} .title-container { overflow: visible; white-space: normal; min-width: 0; }
			${header_css} .header-title { white-space: normal; overflow: visible; line-height: 1.25; word-break: normal; }
			${header_css} .header-subtitle { white-space: normal; overflow: visible; margin-top: 2px; }`;
		document.head.appendChild(style);

		const make = header.prototype.make;
		header.prototype.make = function () {
			make.apply(this, arguments);
			if (this.sidebar && this.sidebar.sidebar_title === SIDEBAR_TITLE && this.$header_title) {
				this.$header_title.text(DISPLAY_TITLE);
			}
		};

		const fetch_related_icons = header.prototype.fetch_related_icons;
		header.prototype.fetch_related_icons = function () {
			let items = fetch_related_icons.apply(this, arguments) || [];
			// Frappe drops the wrong icon from the switcher when the open desk is not found by its label,
			// so the open desk stayed in the list and the other desk could be missing. Show only the OTHER desks.
			const app = frappe.current_app && frappe.current_app.app_name;
			if (app === "ivri_od") {
				const open_label = this.title;
				items = items.filter((i) => i.label !== open_label);
				(frappe.boot.desktop_icons || []).forEach((icon) => {
					if (icon.app !== "ivri_od" || icon.hidden || icon.icon_type !== "Link" || icon.parent_icon) return;
					if (icon.label === open_label) return;
					if (items.some((i) => i.label === icon.label)) return;
					const item = { name: icon.label.toLowerCase(), label: icon.label, url: frappe.utils.get_route_for_icon(icon) };
					const url = frappe.utils.get_desktop_icon(icon.label, frappe.boot.desktop_icon_style);
					if (url) item.icon_url = url;
					else item.icon_html = frappe.utils.desktop_icon(icon.label, "gray", "sm");
					items.push(item);
				});
			}
			items.forEach((item) => {
				if (item.label === SIDEBAR_TITLE) item.label = DISPLAY_TITLE;
			});
			return items;
		};
		header.prototype.__ivri_od_logo = true;
		return true;
	}

	// The Desk bundle defines SidebarHeader; wait for it if this script runs first.
	if (!patch_sidebar_header()) {
		const timer = setInterval(() => {
			if (patch_sidebar_header()) clearInterval(timer);
		}, 50);
		setTimeout(() => clearInterval(timer), 10000);
	}
})();

// Desktop home: the tile that opens this desk shows the same name. The tile keeps its internal label ("Procurement",
// or "ivri_od" before the Procurement tile is shown), because Frappe uses that label as a key; only the shown text changes.
(function () {
	const TILE_LABELS = ["Procurement", "ivri_od"];
	const DISPLAY_TITLE = "Govt. Procurement & CMR";
	const tile = (label) => `.desktop-icon[data-id="${label}"]`;
	const style = document.createElement("style");
	// The three-line name squeezes the icon box below its image height, and the box hides overflow,
	// so the logo was cut at the bottom: keep the box at full size.
	style.textContent =
		TILE_LABELS.map((l) => `${tile(l)} .icon-container`).join(", ") + " { flex-shrink: 0; min-height: 54px; }\n" +
		TILE_LABELS.map((l) => `${tile(l)} .icon-caption`).join(", ") + " { height: auto; }\n" +
		TILE_LABELS.map((l) => `${tile(l)} .icon-title`).join(", ") + " { font-size: 0; white-space: normal; overflow: visible; }\n" +
		TILE_LABELS.map((l) => `${tile(l)} .icon-title::after`).join(", ") +
		` { content: "${DISPLAY_TITLE}"; display: block; font-size: var(--text-sm); white-space: normal; line-height: var(--desktop-icon-line-height); }`;
	document.head.appendChild(style);
})();
