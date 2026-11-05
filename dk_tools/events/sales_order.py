import frappe
from frappe import _


def validate(doc, method):
	"""Bifează requires_installation dacă pe comandă există un articol din grupul „Servicii”."""
	groups = {frappe.get_cached_value("Item", d.item_code, "item_group") for d in doc.items}
	doc.requires_installation = 1 if "Servicii" in groups else 0


def before_submit(doc, method):
	"""Cu workflow activ, comanda se confirmă doar prin acțiunile workflow-ului.

	Un submit direct (frappe.client.submit) ar sări peste condiția de aprobare:
	Frappe ar pune singur starea „Approved”, chiar și pentru comenzi mari.
	"""
	if frappe.get_meta(doc.doctype).get_workflow() and doc.workflow_state != "Approved":
		frappe.throw(_("Sales Order se confirmă doar prin workflow (acțiunile Submit / Approve)."))

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
