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

	frappe.dom.set_style(`
		[data-fieldname="qc_bag_details"] .grid-heading-row,
		[data-fieldname="bag_weight_details"] .grid-heading-row,
		[data-fieldname="type_of_pkt"] .grid-heading-row {
			height: auto !important;
			min-height: 32px;
		}
		[data-fieldname="qc_bag_details"] .grid-heading-row .grid-row,
		[data-fieldname="bag_weight_details"] .grid-heading-row .grid-row,
		[data-fieldname="type_of_pkt"] .grid-heading-row .grid-row {
			height: auto !important;
			min-height: 32px;
		}
		[data-fieldname="qc_bag_details"] .grid-heading-row .grid-static-col,
		[data-fieldname="bag_weight_details"] .grid-heading-row .grid-static-col,
		[data-fieldname="type_of_pkt"] .grid-heading-row .grid-static-col,
		.grid-heading-row .grid-static-col[data-fieldname="jute_pkt_no"],
		.grid-heading-row .grid-static-col[data-fieldname="no_of_plastic_bag"],
		.grid-heading-row .grid-static-col[data-fieldname="jute_bags"],
		.grid-heading-row .grid-static-col[data-fieldname="plastic_bags"],
		.grid-heading-row .grid-static-col[data-fieldname="total_bags"] {
			height: auto !important;
			min-height: 32px;
			padding-top: 6px !important;
			padding-bottom: 6px !important;
			white-space: normal !important;
		}
		[data-fieldname="qc_bag_details"] .grid-heading-row .static-area,
		[data-fieldname="bag_weight_details"] .grid-heading-row .static-area,
		[data-fieldname="type_of_pkt"] .grid-heading-row .static-area,
		.grid-heading-row .grid-static-col[data-fieldname="jute_pkt_no"] .static-area,
		.grid-heading-row .grid-static-col[data-fieldname="no_of_plastic_bag"] .static-area,
		.grid-heading-row .grid-static-col[data-fieldname="jute_bags"] .static-area,
		.grid-heading-row .grid-static-col[data-fieldname="plastic_bags"] .static-area,
		.grid-heading-row .grid-static-col[data-fieldname="total_bags"] .static-area {
			white-space: normal !important;
			word-break: normal !important;
			overflow: visible !important;
			text-overflow: unset !important;
			line-height: 1.25 !important;
		}
	`);
})();
