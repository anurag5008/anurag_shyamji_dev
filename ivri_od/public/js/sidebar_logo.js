// Procurement sidebar header: show the Shyamji "S" emblem instead of the grey first-letter icon.
// Frappe's SidebarHeader skips hidden Desktop Icons, and "Procurement" is a hidden one, so it falls back
// to the generic letter icon and never reads an icon file. Only this one sidebar is changed.
(function () {
	const SIDEBAR_TITLE = "Procurement";
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
