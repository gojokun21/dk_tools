import frappe

def validate(doc, method):
	"""Bifează requires_installation dacă pe comandă există un articol din grupul „Servicii”."""
	groups = {frappe.get_cached_value("Item", d.item_code, "item_group") for d in doc.items}
	doc.requires_installation = 1 if "Servicii" in groups else 0


def on_submit(doc, method):
	"""La submit, o comandă cu instalare generează un Installation Request."""
	if not doc.requires_installation:
		return
	frappe.get_doc(
		{
			"doctype": "Installation Request",
			"customer": doc.customer,
			"sales_order": doc.name,
			"status": "Open",
			"notes": doc.installation_notes,
		}
	).insert(ignore_permissions=True)
