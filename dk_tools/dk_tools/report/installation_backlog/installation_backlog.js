// Copyright (c) 2026, Sorin and contributors
// For license information, please see license.txt

// Filtrele de deasupra tabelului; valorile lor ajung în `filters` din installation_backlog.py
frappe.query_reports["Installation Backlog"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOpen\nScheduled\nDone\nCancelled",
		},
		{
			fieldname: "technician",
			label: __("Technician"),
			fieldtype: "Link",
			options: "User",
		},
	],
};
