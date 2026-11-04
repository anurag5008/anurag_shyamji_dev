app_name = "ivri_od"
app_title = "ivri_od"
app_publisher = "Profezzo"
app_description = "To manage rice mill of odisha"
app_email = "rabadajit66@gmail.com"
app_license = "mit"

after_migrate = ["ivri_od.procurement.procurement_workspace.ensure_procurement_workspace_after_migrate"]

boot_session = ["ivri_od.procurement.boot_session.extend_procurement_boot"]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "ivri_od",
		"logo": "/assets/ivri_od/images/procurement.svg",
		"title": "ivri_od",
		"route": "/desk/procurement",
		"has_permission": "ivri_od.api.permission.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_js = [
	"/assets/ivri_od/js/disable_quick_entry.js",
	"/assets/ivri_od/js/sidebar_logo.js?v=3",
	"/assets/ivri_od/js/warehouse_wise_stock_balance.js?v=2",
	"/assets/ivri_od/js/mill_reminder_banner.js?v=12",
	"portal_detail_table.bundle.js",
]
# app_include_css = "/assets/ivri_od/css/ivri_od.css"
# include js, css files in header of web template
# web_include_css = "/assets/ivri_od/css/ivri_od.css"
# web_include_js = "/assets/ivri_od/js/ivri_od.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ivri_od/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Report": "public/js/procurement_report_redirect.js",
	"GRN Note": "public/js/grn_stock_posting.js",
	"Purchase Order": "public/js/purchase_order_mill.js",
	"Purchase Receipt": "public/js/purchase_receipt_mill.js",
	"Purchase Invoice": "public/js/purchase_invoice_mill.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "ivri_od/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": ["ivri_od.procurement.vehicle_statement.debit_vouchers", "ivri_od.procurement.vehicle_statement.vehicle_lines"],
}

# Installation
# ------------

# before_install = "ivri_od.install.before_install"
# after_install = "ivri_od.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "ivri_od.uninstall.before_uninstall"
# after_uninstall = "ivri_od.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ivri_od.utils.before_app_install"
# after_app_install = "ivri_od.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ivri_od.utils.before_app_uninstall"
# after_app_uninstall = "ivri_od.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "ivri_od.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ivri_od.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# Portal sites and their sections (SCMS, DCRO, WINGS) used by Portal Data Extraction.
# Purchase Receipt shows only what the plant staff need: every other field is hidden by a Property Setter.
# (document, field, property); the values are in fixtures/property_setter.json.
PURCHASE_RECEIPT_SETTERS = [
	("Purchase Receipt", "currency_and_price_list", "hidden"),
	("Purchase Receipt", "taxes_charges_section", "hidden"),
	("Purchase Receipt", "taxes_section", "hidden"),
	("Purchase Receipt", "totals", "hidden"),
	("Purchase Receipt", "totals_section", "hidden"),
	("Purchase Receipt", "base_totals_section", "hidden"),
	("Purchase Receipt", "section_break_42", "hidden"),
	("Purchase Receipt", "sec_tax_breakup", "hidden"),
	("Purchase Receipt", "pricing_rule_details", "hidden"),
	("Purchase Receipt", "raw_material_details", "hidden"),
	("Purchase Receipt", "address_and_contact_tab", "hidden"),
	("Purchase Receipt", "terms_tab", "hidden"),
	("Purchase Receipt", "more_info_tab", "hidden"),
	("Purchase Receipt", "subscription_detail", "hidden"),
	("Purchase Receipt", "printing_settings", "hidden"),
	("Purchase Receipt", "transporter_info", "hidden"),
	("Purchase Receipt", "additional_info_section", "hidden"),
	("Purchase Receipt", "status_section", "hidden"),
	("Purchase Receipt", "subcontracting_receipt", "hidden"),
	("Purchase Receipt", "set_posting_time", "hidden"),
	("Purchase Receipt", "posting_time", "hidden"),
	("Purchase Receipt", "apply_putaway_rule", "hidden"),
	("Purchase Receipt", "is_return", "hidden"),
	("Purchase Receipt", "return_against", "hidden"),
	("Purchase Receipt", "scan_barcode", "hidden"),
	("Purchase Receipt", "last_scanned_warehouse", "hidden"),
	("Purchase Receipt", "set_from_warehouse", "hidden"),
	("Purchase Receipt", "rejected_warehouse", "hidden"),
	("Purchase Receipt", "is_subcontracted", "hidden"),
	("Purchase Receipt", "supplier_warehouse", "hidden"),
	("Purchase Receipt", "project", "hidden"),
	("Purchase Receipt", "total_net_weight", "hidden"),
	("Purchase Receipt", "base_total", "hidden"),
	("Purchase Receipt", "base_net_total", "hidden"),
	("Purchase Receipt", "net_total", "hidden"),
	("Purchase Receipt", "get_current_stock", "hidden"),
	("Purchase Receipt Item", "barcode", "hidden"),
	("Purchase Receipt Item", "has_item_scanned", "hidden"),
	("Purchase Receipt Item", "product_bundle", "hidden"),
	("Purchase Receipt Item", "description", "hidden"),
	("Purchase Receipt Item", "item_group", "hidden"),
	("Purchase Receipt Item", "image_view", "hidden"),
	("Purchase Receipt Item", "received_qty", "hidden"),
	("Purchase Receipt Item", "rejected_qty", "hidden"),
	("Purchase Receipt Item", "stock_uom", "hidden"),
	("Purchase Receipt Item", "conversion_factor", "hidden"),
	("Purchase Receipt Item", "retain_sample", "hidden"),
	("Purchase Receipt Item", "sample_quantity", "hidden"),
	("Purchase Receipt Item", "received_stock_qty", "hidden"),
	("Purchase Receipt Item", "stock_qty", "hidden"),
	("Purchase Receipt Item", "returned_qty", "hidden"),
	("Purchase Receipt Item", "price_list_rate", "hidden"),
	("Purchase Receipt Item", "base_price_list_rate", "hidden"),
	("Purchase Receipt Item", "margin_type", "hidden"),
	("Purchase Receipt Item", "margin_rate_or_amount", "hidden"),
	("Purchase Receipt Item", "rate_with_margin", "hidden"),
	("Purchase Receipt Item", "discount_percentage", "hidden"),
	("Purchase Receipt Item", "discount_amount", "hidden"),
	("Purchase Receipt Item", "distributed_discount_amount", "hidden"),
	("Purchase Receipt Item", "base_rate_with_margin", "hidden"),
	("Purchase Receipt Item", "base_rate", "hidden"),
	("Purchase Receipt Item", "base_amount", "hidden"),
	("Purchase Receipt Item", "stock_uom_rate", "hidden"),
	("Purchase Receipt Item", "is_free_item", "hidden"),
	("Purchase Receipt Item", "net_rate", "hidden"),
	("Purchase Receipt Item", "net_amount", "hidden"),
	("Purchase Receipt Item", "item_tax_template", "hidden"),
	("Purchase Receipt Item", "base_net_rate", "hidden"),
	("Purchase Receipt Item", "base_net_amount", "hidden"),
	("Purchase Receipt Item", "landed_cost_voucher_amount", "hidden"),
	("Purchase Receipt Item", "amount_difference_with_purchase_invoice", "hidden"),
	("Purchase Receipt Item", "billed_amt", "hidden"),
	("Purchase Receipt Item", "rejected_warehouse", "hidden"),
	("Purchase Receipt Item", "material_request", "hidden"),
	("Purchase Receipt Item", "purchase_invoice", "hidden"),
	("Purchase Receipt Item", "allow_zero_valuation_rate", "hidden"),
	("Purchase Receipt Item", "return_qty_from_rejected_warehouse", "hidden"),
	("Purchase Receipt Item", "asset_location", "hidden"),
	("Purchase Receipt Item", "asset_category", "hidden"),
	("Purchase Receipt Item", "schedule_date", "hidden"),
	("Purchase Receipt Item", "quality_inspection", "hidden"),
	("Purchase Receipt Item", "delivery_note_item", "hidden"),
	("Purchase Receipt Item", "putaway_rule", "hidden"),
	("Purchase Receipt Item", "add_serial_batch_for_rejected_qty", "hidden"),
	("Purchase Receipt Item", "rejected_serial_and_batch_bundle", "hidden"),
	("Purchase Receipt Item", "serial_no", "hidden"),
	("Purchase Receipt Item", "rejected_serial_no", "hidden"),
	("Purchase Receipt Item", "include_exploded_items", "hidden"),
	("Purchase Receipt Item", "bom", "hidden"),
	("Purchase Receipt Item", "weight_per_unit", "hidden"),
	("Purchase Receipt Item", "total_weight", "hidden"),
	("Purchase Receipt Item", "weight_uom", "hidden"),
	("Purchase Receipt Item", "manufacturer", "hidden"),
	("Purchase Receipt Item", "manufacturer_part_no", "hidden"),
	("Purchase Receipt Item", "expense_account", "hidden"),
	("Purchase Receipt Item", "wip_composite_asset", "hidden"),
	("Purchase Receipt Item", "provisional_expense_account", "hidden"),
	("Purchase Receipt Item", "project", "hidden"),
	("Purchase Receipt Item", "cost_center", "hidden"),
	("Purchase Receipt Item", "sales_order", "hidden"),
	("Purchase Receipt Item", "page_break", "hidden"),
	("Purchase Receipt", "sec_warehouse", "hidden"),
	("Purchase Receipt Item", "item_code", "columns"),
	("Purchase Receipt Item", "rate", "reqd"),
	("Purchase Receipt Item", "rate", "mandatory_depends_on"),
	("Purchase Receipt Item", "rate", "depends_on"),
	("Purchase Receipt", "set_warehouse", "label"),
	("Purchase Receipt Item", "qty", "label"),
	("Purchase Receipt Item", "item_code", "label"),
	("Purchase Receipt Item", "rejected_qty", "in_list_view"),
	("Purchase Receipt Item", "warehouse", "in_list_view"),
	("Purchase Receipt Item", "uom", "in_list_view"),
	("Purchase Receipt Item", "qty", "columns"),
	("Purchase Receipt Item", "rate", "columns"),
	("Purchase Receipt Item", "amount", "columns"),
	("Purchase Receipt Item", "uom", "columns"),
]

# Purchase Invoice: made from a Purchase Receipt or a Purchase Order, it shows only what the plant staff need.
_PI_FIELDS = (
	"print_company_name invoice_conditions_section gunny_condition dust_condition payment_mode "
	"invoice_conditions_col delivery_type location_name invoice_vehicle_section vehicle_number driver "
	"invoice_vehicle_col invoice_quality_section moisture invoice_quality_col dust_kg "
	"invoice_hamali_section hamali_payer hamali_rate invoice_hamali_col total_hamali quality_pds_rate_1 "
	"quality_pds_rate_2 quality_pds_rate_3 vehicle_ownership transporter freight_charges "
	"quality_pds_section quality_pds_col quality_pds_qty_1 quality_pds_qty_2 quality_pds_qty_3 "
	"quality_pds_amount quality_pds_pct_col quality_pds_pct_1 quality_pds_pct_2 quality_pds_pct_3 "
	"quality_pds_percentage purchase_order purchase_receipt invoice_deduction_section deduction_amount "
	"invoice_deduction_col deduction_reason invoice_final_section total_final_amount "
)
_PII_FIELDS = (
	"quality dimension avg_wt ordered_qty rate_per_mt oil_percentage actual_oil_percentage "
	"oil_rate_per_mt "
)
_PI_HIDDEN = (
	"tax_id posting_time set_posting_time is_paid is_return return_against update_outstanding_for_self "
	"update_billed_amount_in_purchase_order update_billed_amount_in_purchase_receipt apply_tds "
	"amended_from accounting_dimensions_section cost_center project currency_and_price_list currency "
	"conversion_rate use_transaction_date_exchange_rate buying_price_list price_list_currency "
	"plc_conversion_rate ignore_pricing_rule sec_warehouse scan_barcode last_scanned_warehouse "
	"update_stock set_warehouse set_from_warehouse is_subcontracted rejected_warehouse supplier_warehouse "
	"total_net_weight base_total base_net_total claimed_landed_cost_amount net_total taxes_section "
	"tax_category taxes_and_charges shipping_rule incoterm named_place section_break_51 taxes totals "
	"base_taxes_and_charges_added base_taxes_and_charges_deducted base_total_taxes_and_charges "
	"taxes_and_charges_added taxes_and_charges_deducted total_taxes_and_charges totals_section "
	"use_company_roundoff_cost_center grand_total in_words disable_rounded_total rounding_adjustment "
	"rounded_total base_totals_section base_grand_total base_in_words base_rounding_adjustment "
	"base_rounded_total section_break_ttrv total_advance outstanding_amount section_tax_withholding_entry "
	"tax_withholding_group ignore_tax_withholding_threshold override_tax_withholding_entries "
	"tax_withholding_entries section_break_44 apply_discount_on base_discount_amount "
	"additional_discount_percentage discount_amount sec_tax_breakup other_charges_calculation "
	"item_wise_tax_details pricing_rule_details pricing_rules raw_materials_supplied supplied_items "
	"payments_tab payments_section mode_of_payment base_paid_amount clearance_date cash_bank_account "
	"paid_amount advances_section allocate_advances_automatically only_include_allocated_payments "
	"get_advances advances write_off write_off_amount base_write_off_amount write_off_account "
	"write_off_cost_center address_and_contact_tab section_addresses supplier_address address_display "
	"contact_person contact_display contact_mobile contact_email company_shipping_address_section "
	"dispatch_address dispatch_address_display shipping_address shipping_address_display "
	"company_billing_address_section billing_address billing_address_display terms_tab "
	"payment_schedule_section payment_terms_template ignore_default_payment_terms_template "
	"payment_schedule terms_section_break tc_name terms more_info_tab status_section status per_received "
	"accounting_details_section credit_to party_account_currency is_opening against_expense_account "
	"unrealized_profit_loss_account subscription_section subscription from_date to_date "
	"automation_section auto_repeat update_auto_repeat_reference printing_settings letter_head "
	"group_same_items select_print_heading language sb_14 on_hold release_date hold_comment "
	"additional_info_section is_internal_supplier title represents_company supplier_group sender "
	"inter_company_invoice_reference is_old_subcontracting_flow remarks "
)
_PII_HIDDEN = (
	"product_bundle description_section description brand item_group image image_view quantity_and_rate "
	"received_qty rejected_qty conversion_factor stock_uom stock_qty sec_break1 price_list_rate "
	"base_price_list_rate section_break_26 margin_type margin_rate_or_amount rate_with_margin "
	"discount_percentage discount_amount distributed_discount_amount base_rate_with_margin sec_break2 "
	"item_tax_template tax_withholding_category base_rate base_amount pricing_rules stock_uom_rate "
	"is_free_item apply_tds allow_zero_valuation_rate section_break_22 net_rate net_amount base_net_rate "
	"base_net_amount valuation_rate sales_incoming_rate item_tax_amount landed_cost_voucher_amount "
	"rm_supp_cost warehouse_section warehouse add_serial_batch_bundle serial_and_batch_bundle "
	"use_serial_batch_fields from_warehouse quality_inspection rejected_warehouse "
	"rejected_serial_and_batch_bundle section_break_rqbe serial_no rejected_serial_no batch_no "
	"manufacture_details manufacturer manufacturer_part_no accounting expense_account wip_composite_asset "
	"is_fixed_asset asset_location asset_category deferred_expense_section deferred_expense_account "
	"service_stop_date enable_deferred_expense service_start_date service_end_date reference "
	"item_tax_rate bom include_exploded_items purchase_invoice_item po_detail pr_detail "
	"sales_invoice_item material_request material_request_item delivered_by_supplier item_weight_details "
	"weight_per_unit total_weight weight_uom accounting_dimensions_section project cost_center "
	"section_break_82 page_break "
)
PURCHASE_INVOICE_SETTERS = (
	[("Purchase Invoice", f, "hidden") for f in _PI_HIDDEN.split()]
	+ [("Purchase Invoice Item", f, "hidden") for f in _PII_HIDDEN.split()]
	+ [
		("Purchase Invoice Item", "item_code", "label"),
		("Purchase Invoice Item", "qty", "label"),
		("Purchase Invoice Item", "item_code", "columns"),
		("Purchase Invoice Item", "qty", "columns"),
		("Purchase Invoice Item", "uom", "in_list_view"),
		("Purchase Invoice Item", "uom", "columns"),
		("Purchase Invoice Item", "rate", "columns"),
		("Purchase Invoice Item", "amount", "columns"),
		("Purchase Invoice Item", "rate", "reqd"),
		("Purchase Invoice Item", "rate", "mandatory_depends_on"),
		("Purchase Invoice Item", "rate", "depends_on"),
		("Purchase Invoice Item", "item_name", "in_list_view"),
	]
)
PURCHASE_INVOICE_CUSTOM_FIELDS = [f"Purchase Invoice-{f}" for f in _PI_FIELDS.split()] + [f"Purchase Invoice Item-{f}" for f in _PII_FIELDS.split()]

fixtures = [
	{"dt": "Portal Site"},
	{"dt": "Custom Field", "filters": [["name", "in", ["Stock Entry-procurement_source_section", "Stock Entry-grn_note", "Stock Entry-weigh_bridge_measurement", "Stock Entry-pass_unique_key", "Stock Entry-procurement_source_col", "Stock Entry-ppc", "Stock Entry-transit_pass_no", "Stock Entry-operating_unit", "Stock Entry Detail-no_of_bags", "Warehouse-operating_unit", "Warehouse-physical_location", "Batch-season", "Batch-procurement_type", "Batch-quality_grade", "Batch-source_grn", "Batch-operating_unit", "Stock Entry-ownership_section", "Stock Entry-transfer_kind", "Stock Entry-ownership_transfer_reason", "Purchase Order-mill_details_section", "Purchase Order-mill_details_col", "Purchase Order-gunny_condition", "Purchase Order-dust_condition", "Purchase Order-delivery_type", "Purchase Order-location_name", "Purchase Order-hamali_section", "Purchase Order-hamali_rate", "Purchase Order-hamali_payer", "Purchase Order-hamali_col", "Purchase Order-total_hamali", "Purchase Order-vehicle_section", "Purchase Order-vehicle_ownership", "Purchase Order-transporter", "Purchase Order-vehicle_number", "Purchase Order-vehicle_col", "Purchase Order-driver", "Purchase Order-print_company_name", *PURCHASE_INVOICE_CUSTOM_FIELDS, "Purchase Order Item-rate_per_mt", "Purchase Order Item-oil_percentage", "Purchase Receipt Item-rate_per_mt", "Purchase Receipt Item-oil_percentage", "Purchase Receipt Item-actual_oil_percentage", "Purchase Receipt Item-oil_rate_per_mt", "Purchase Receipt-print_company_name", "Purchase Receipt-receipt_deal_section", "Purchase Receipt-deal_amount", "Purchase Receipt-amount_difference", "Purchase Receipt Item-po_rate", "Purchase Receipt-quality_pds_section", "Purchase Receipt-quality_pds_percentage", "Purchase Receipt-quality_pds_pct_col", "Purchase Receipt-quality_pds_pct_1", "Purchase Receipt-quality_pds_pct_2", "Purchase Receipt-quality_pds_pct_3", "Purchase Receipt-quality_pds_col", "Purchase Receipt-quality_pds_qty_1", "Purchase Receipt-quality_pds_qty_2", "Purchase Receipt-quality_pds_qty_3", "Purchase Receipt-quality_pds_amount", "Purchase Receipt-vehicle_ownership", "Purchase Receipt-transporter", "Purchase Receipt-freight_charges", "Purchase Receipt-purchase_order", "Purchase Receipt-quality_pds_rate_1", "Purchase Receipt-quality_pds_rate_2", "Purchase Receipt-quality_pds_rate_3", "Purchase Receipt Item-quality", "Purchase Receipt Item-dimension", "Purchase Receipt Item-avg_wt", "Purchase Receipt Item-ordered_qty", "Purchase Receipt Item-receipt_status", "Purchase Receipt-receipt_conditions_section", "Purchase Receipt-gunny_condition", "Purchase Receipt-dust_condition", "Purchase Receipt-payment_mode", "Purchase Receipt-receipt_conditions_col", "Purchase Receipt-delivery_type", "Purchase Receipt-location_name", "Purchase Receipt-receipt_vehicle_section", "Purchase Receipt-vehicle_number", "Purchase Receipt-driver", "Purchase Receipt-receipt_vehicle_col", "Purchase Receipt-weigh_bridge_measurement", "Purchase Receipt-quality_check", "Purchase Receipt-receipt_quality_section", "Purchase Receipt-moisture", "Purchase Receipt-receipt_quality_col", "Purchase Receipt-dust_kg", "Purchase Receipt-receipt_hamali_section", "Purchase Receipt-hamali_payer", "Purchase Receipt-hamali_rate", "Purchase Receipt-receipt_hamali_col", "Purchase Receipt-total_hamali", "Purchase Receipt-receipt_final_section", "Purchase Receipt-receipt_status", "Purchase Receipt-receipt_final_col", "Purchase Receipt-total_final_amount", "Purchase Order-freight_charges", "Purchase Order-payment_mode", "Purchase Order-final_amount_section", "Purchase Order-total_final_amount", "Purchase Order Item-quality", "Purchase Order Item-dimension", "Purchase Order Item-avg_wt", "Purchase Order-quality_pds_rate_1", "Purchase Order-quality_pds_rate_2", "Purchase Order-quality_pds_rate_3"]]]},
	{"dt": "Property Setter", "filters": [["name", "in", ["Purchase Order-main-field_order", "Purchase Order Item-item_code-label", "Purchase Order Item-item_code-columns", "Purchase Order Item-schedule_date-in_list_view", "Purchase Order Item-warehouse-in_list_view", "Purchase Order-currency_and_price_list-hidden", "Purchase Order-taxes_section-hidden", "Purchase Order-section_break_52-hidden", "Purchase Order-totals-hidden", "Purchase Order-totals_section-hidden", "Purchase Order-discount_section-depends_on", "Purchase Order-apply_discount_on-default", "Purchase Order-additional_discount_percentage-label", "Purchase Order-discount_amount-label", "Purchase Order-base_discount_amount-label", "Purchase Order-advance_paid-hidden", "Purchase Order-set_warehouse-hidden", "Purchase Order-scan_barcode-hidden","Purchase Order-company-reqd", "Purchase Order-base_total-hidden", "Purchase Order-base_net_total-hidden", "Purchase Order-net_total-hidden", "Purchase Order-supplier-reqd","Purchase Order Item-rate-reqd", "Purchase Order Item-warehouse-hidden", "Purchase Receipt-supplier-reqd", *[f"{dt}-{f}-{p}" for dt, f, p in PURCHASE_INVOICE_SETTERS], "Purchase Invoice-main-default_print_format", "Vehicle Wise Statement-main-default_print_format", "Purchase Receipt-main-field_order", "Purchase Receipt-main-default_print_format", *[f"{dt}-{f}-{p}" for dt, f, p in PURCHASE_RECEIPT_SETTERS], "Purchase Order Item-rate-mandatory_depends_on", "Purchase Order Item-rate-depends_on"]]]},
	{"dt": "Print Format", "filters": [["name", "in", ["Annexure-1 Verification Report", "Purchase Order - Shyamji", "Purchase Receipt - Shyamji", "Purchase Invoice - Shyamji", "Vehicle Wise Statement - Shyamji", "Debit Voucher - Shyamji"]]]},
]

doc_events = {
	"DocType": {
		"on_update": "ivri_od.form_layout.sync_saved_field_order",
	},
	"Stock Entry": {
		"validate": [
			"ivri_od.procurement.stock_posting.validate_stock_entry",
			"ivri_od.procurement.inventory_foundation.validate_stock_entry_foundation",
		],
		"before_submit": "ivri_od.procurement.inventory_foundation.check_bag_balance_before_submit",
		"on_submit": "ivri_od.procurement.inventory_foundation.record_bag_ledger",
		"on_cancel": [
			"ivri_od.procurement.stock_posting.on_cancel_stock_entry",
			"ivri_od.procurement.inventory_foundation.reverse_bag_ledger",
		],
	},
	"Purchase Order": {
		"before_validate": ["ivri_od.procurement.purchase_order_mill.install_trip_amount", "ivri_od.procurement.purchase_order_mill.set_default_company", "ivri_od.procurement.purchase_order_mill.align_cost_center_with_company", "ivri_od.procurement.purchase_order_mill.apply_bran_rate", "ivri_od.procurement.purchase_order_mill.clear_discount_unless_cash"],
		"validate": "ivri_od.procurement.purchase_order_mill.validate_purchase_order",
	},
	"Purchase Receipt": {
		"before_validate": ["ivri_od.procurement.purchase_receipt_mill.sync_pds_quantity", "ivri_od.procurement.purchase_order_mill.apply_bran_rate", "ivri_od.procurement.purchase_receipt_mill.require_received_quantity"],
		"before_submit": ["ivri_od.procurement.purchase_receipt_mill.require_pds_split_on_submit", "ivri_od.procurement.purchase_receipt_mill.require_actual_oil_on_submit"],
		"validate": "ivri_od.procurement.purchase_receipt_mill.validate_purchase_receipt",
	},
	"Purchase Invoice": {
		"before_validate": ["ivri_od.procurement.purchase_receipt_mill.sync_pds_quantity", "ivri_od.procurement.purchase_order_mill.apply_bran_rate", "ivri_od.procurement.purchase_invoice_mill.set_deductions_as_discount"],
		"validate": "ivri_od.procurement.purchase_invoice_mill.validate_purchase_invoice",
		"before_submit": ["ivri_od.procurement.purchase_receipt_mill.require_pds_split_on_submit", "ivri_od.procurement.purchase_receipt_mill.require_actual_oil_on_submit"],
	},
	"Mill Master": {
		"validate": "ivri_od.procurement.inventory_foundation.validate_mill_master_mapping",
	},
	"GRN Note": {
		"on_update": "ivri_od.procurement.stock_posting.guard_grn_note",
		"on_trash": "ivri_od.procurement.stock_posting.guard_grn_note_trash",
	},
	"Weigh Bridge Measurement": {
		"on_update": "ivri_od.procurement.stock_posting.guard_weigh_bridge",
		"on_trash": "ivri_od.procurement.stock_posting.guard_weigh_bridge_trash",
	},
	"Warehouse": {
		"validate": "ivri_od.procurement.stock_posting.validate_warehouse",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"ivri_od.tasks.all"
# 	],
# 	"daily": [
# 		"ivri_od.tasks.daily"
# 	],
# 	"hourly": [
# 		"ivri_od.tasks.hourly"
# 	],
# 	"weekly": [
# 		"ivri_od.tasks.weekly"
# 	],
# 	"monthly": [
# 		"ivri_od.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "ivri_od.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "ivri_od.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ivri_od.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "ivri_od.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# Warehouse Wise Stock Balance shows Paddy Stock from the GRN Notes (procurement/paddy_stock_report.py)
before_request = ["ivri_od.procurement.paddy_stock_report.install", "ivri_od.procurement.purchase_order_mill.install_trip_amount", "ivri_od.procurement.purchase_order_mill.install_no_auto_rate", "ivri_od.procurement.purchase_order_mill.install_no_warehouse_check", "ivri_od.procurement.purchase_receipt_mill.install_ordered_qty_on_receipt", "ivri_od.procurement.purchase_invoice_mill.install_ordered_qty_on_invoice"]
before_job = ["ivri_od.procurement.paddy_stock_report.install", "ivri_od.procurement.purchase_order_mill.install_trip_amount", "ivri_od.procurement.purchase_order_mill.install_no_auto_rate", "ivri_od.procurement.purchase_order_mill.install_no_warehouse_check", "ivri_od.procurement.purchase_receipt_mill.install_ordered_qty_on_receipt", "ivri_od.procurement.purchase_invoice_mill.install_ordered_qty_on_invoice"]
# before_request = ["ivri_od.utils.before_request"]
# after_request = ["ivri_od.utils.after_request"]

# Job Events
# ----------
# before_job = ["ivri_od.utils.before_job"]
# after_job = ["ivri_od.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"ivri_od.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

