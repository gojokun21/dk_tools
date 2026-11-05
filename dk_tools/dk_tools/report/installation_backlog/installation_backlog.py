# Copyright (c) 2026, Sorin and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters: dict | None = None):
	"""Punctul de intrare: Frappe îl cheamă la fiecare rulare a raportului (și la schimbarea filtrelor)."""
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns() -> list[dict]:
	"""Coloanele tabelului: se descriu la fel ca niște câmpuri de DocType."""
	return [
		{"label": _("Installation Request"), "fieldname": "name", "fieldtype": "Link",
			"options": "Installation Request", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer",
			"width": 180},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link",
			"options": "Sales Order", "width": 170},
		{"label": _("Scheduled Date"), "fieldname": "scheduled_date", "fieldtype": "Date", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Technician"), "fieldname": "technician", "fieldtype": "Link", "options": "User",
			"width": 180},
	]


def get_data(filters: dict) -> list[dict]:
	"""Rândurile tabelului: cererile de instalare, filtrate după ce a ales userul."""
	conditions = {}
	if filters.get("status"):
		conditions["status"] = filters["status"]
	else:
		# implicit: tot ce nu e închis
		conditions["status"] = ["not in", ["Done", "Cancelled"]]
	if filters.get("technician"):
		conditions["technician"] = filters["technician"]

	# get_list (nu get_all) respectă permisiunile userului care rulează raportul
	return frappe.get_list(
		"Installation Request",
		filters=conditions,
		fields=["name", "customer", "sales_order", "scheduled_date", "status", "technician"],
		order_by="scheduled_date asc, creation asc",
	)
