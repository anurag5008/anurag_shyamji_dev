// Always open the full form instead of the quick-entry dialog.
(function () {
	const _make_quick_entry = frappe.ui.form.make_quick_entry;

	frappe.ui.form.make_quick_entry = function (
		doctype,
		after_insert,
		init_callback,
		doc,
		force,
		skip_insert
	) {
		if (force) {
			return _make_quick_entry.apply(this, arguments);
		}

		return new Promise((resolve) => {
			frappe.model.with_doctype(doctype, () => {
				if (!doc) {
					doc = frappe.model.get_new_doc(doctype, null, null, true);
				}
				if (frappe.route_options && $.isPlainObject(frappe.route_options)) {
					$.extend(doc, frappe.route_options);
					frappe.route_options = null;
				}

				frappe.set_route("Form", doctype, doc.name).then(() => {
					if (init_callback) {
						init_callback(doc);
					}
					resolve();
				});
			});
		});
	};
})();
