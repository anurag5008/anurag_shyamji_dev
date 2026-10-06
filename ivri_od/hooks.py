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
app_include_js = "/assets/ivri_od/js/disable_quick_entry.js"
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
doctype_js = {"Report": "public/js/procurement_report_redirect.js"}
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
# jinja = {
# 	"methods": "ivri_od.utils.jinja_methods",
# 	"filters": "ivri_od.utils.jinja_filters"
# }

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

doc_events = {
	"DocType": {
		"on_update": "ivri_od.form_layout.sync_saved_field_order",
	}
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

