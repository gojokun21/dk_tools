import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "seed_data.json"
STATE_FILE = HERE / "seed_state.json"
TODAY = date.today()
NEXT_WEEK = str(TODAY + timedelta(days=7))

# Funcțiile de mapare din ERPNext (secțiunea 6.3)
MAKE_PO_FROM_MR = "erpnext.stock.doctype.material_request.material_request.make_purchase_order"
MAKE_PR = "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt"
MAKE_PI = "erpnext.stock.doctype.purchase_receipt.purchase_receipt.make_purchase_invoice"
MAKE_SO_FROM_QTN = "erpnext.selling.doctype.quotation.quotation.make_sales_order"
MAKE_DN = "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note"
MAKE_SI = "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice"
MAKE_SE = "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry"
GET_PE = "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry"
RUN_REPORT = "frappe.desk.query_report.run"
# Din ziua 7: o acțiune de workflow (Submit / Send for Approval / Approve), ca butoanele din Actions
APPLY_WORKFLOW = "frappe.model.workflow.apply_workflow"

class ERPError(Exception):
    pass


class ERP:
    def __init__(self, url, key, secret):
        self.url = url.rstrip("/")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{secret}"

    def _check(self, r):
        if r.ok:
            return r.json()
        try:
            body = r.json()
        except ValueError:
            body = {}
        msg = body.get("exception") or body.get("_server_messages") or r.text[:500]
        raise ERPError(f"{r.request.method} {r.url} -> {r.status_code}\n{msg}")

    def get(self, doctype, name):
        """Documentul complet sau None dacă nu există (404)."""
        r = self.s.get(f"{self.url}/api/resource/{quote(doctype)}/{quote(str(name), safe='')}")
        if r.status_code == 404:
            return None
        return self._check(r)["data"]

    def get_list(self, doctype, filters=None, fields=("name",)):
        params = {
            "filters": json.dumps(filters or []),
            "fields": json.dumps(list(fields)),
            "limit_page_length": 0,
        }
        r = self.s.get(f"{self.url}/api/resource/{quote(doctype)}", params=params)
        return self._check(r)["data"]

    def insert(self, doc):
        r = self.s.post(f"{self.url}/api/resource/{quote(doc['doctype'])}", json=doc)
        return self._check(r)["data"]

    def call(self, method, **kwargs):
        r = self.s.post(f"{self.url}/api/method/{method}", json=kwargs)
        return self._check(r)["message"]

    def submit(self, doc):
        return self.call("frappe.client.submit", doc=doc)

    def ensure(self, doc, name):
        """Creează doar dacă nu există (pentru master data cu nume predictibil)."""
        existing = self.get(doc["doctype"], name)
        if existing:
            return existing
        print(f"  + {doc['doctype']}: {name}")
        return self.insert(doc)


def whoami(erp):
    return erp.call("frappe.auth.get_logged_user")


# ---------------------------------------------------------------- stare (idempotență)


class State:
    """seed_state.json: ID pas seed -> nume document ERPNext, separat pe fiecare site.

    Dacă site-ul a fost recreat (altă dată de creare a companiei), starea veche se ignoră.
    """

    def __init__(self, erp, company):
        self.all = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
        created = erp.get("Company", company)["creation"]
        site = self.all.get(erp.url, {})
        if site.get("_company_created") != created:
            site = {"_company_created": created}
        self.all[erp.url] = self.data = site
        self.save()

    def get(self, key):
        return self.data.get(key)

    def set(self, key, name):
        self.data[key] = name
        self.save()

    def save(self):
        STATE_FILE.write_text(json.dumps(self.all, indent=2, ensure_ascii=False), encoding="utf-8")


def step(erp, state, key, doctype, build, submit=None):
    """Rulează pasul `key` o singură dată: build() -> document nesalvat, apoi insert + submit."""
    name = state.get(key)
    doc = erp.get(doctype, name) if name else None
    if doc and doc["docstatus"] == 1:
        print(f"  = {key}: {name} (exista deja)")
        return doc
    if not doc or doc["docstatus"] == 2:
        doc = erp.insert(build())
        state.set(key, doc["name"])
    doc = (submit or erp.submit)(doc)
    print(f"  + {key}: {doc['name']}")
    return doc


# ---------------------------------------------------------------- master data


def seed_master_data(erp, data):
    company = data["company"]
    wh = data["warehouses"]
    print("Master data")
    for uom in data["uoms"]:
        erp.ensure({"doctype": "UOM", "uom_name": uom, "must_be_whole_number": 1}, uom)
    for group in data["item_groups"]:
        erp.ensure(
            {"doctype": "Item Group", "item_group_name": group, "parent_item_group": "All Item Groups"}, group
        )
    for key in ("raw", "wip", "fg"):
        name = wh[key]
        erp.ensure(
            {
                "doctype": "Warehouse",
                "warehouse_name": name.rsplit(" - ", 1)[0],
                "parent_warehouse": wh["parent"],
                "company": company,
            },
            name,
        )
    for item in data["items"]:
        doc = {
            "doctype": "Item",
            "item_code": item["item_code"],
            "item_name": item["item_name"],
            "item_group": item["item_group"],
            "stock_uom": data["uoms"][0],
            "is_stock_item": item["is_stock_item"],
            "include_item_in_manufacturing": item["is_stock_item"],
        }
        if item.get("default_warehouse"):
            doc["item_defaults"] = [{"company": company, "default_warehouse": item["default_warehouse"]}]
        erp.ensure(doc, item["item_code"])
        for price_list, field in (("Standard Buying", "buying_rate"), ("Standard Selling", "selling_rate")):
            if field in item and not erp.get_list(
                "Item Price", [["item_code", "=", item["item_code"]], ["price_list", "=", price_list]]
            ):
                print(f"  + Item Price: {item['item_code']} / {price_list}")
                erp.insert(
                    {
                        "doctype": "Item Price",
                        "item_code": item["item_code"],
                        "price_list": price_list,
                        "price_list_rate": item[field],
                    }
                )
    for s in data["suppliers"]:
        erp.ensure({"doctype": "Supplier", "supplier_type": "Company", **s}, s["supplier_name"])
    for c in data["customers"]:
        erp.ensure({"doctype": "Customer", "customer_type": "Company", **c}, c["customer_name"])
    return ensure_bom(erp, data)


def ensure_bom(erp, data):
    bom = data["bom"]
    existing = erp.get_list(
        "BOM", [["item", "=", bom["item"]], ["is_default", "=", 1], ["docstatus", "=", 1]]
    )
    if existing:
        return existing[0]["name"]
    doc = erp.insert(
        {
            "doctype": "BOM",
            "item": bom["item"],
            "company": data["company"],
            "quantity": bom["quantity"],
            "is_active": 1,
            "is_default": 1,
            "rm_cost_as_per": "Price List",
            "buying_price_list": "Standard Buying",
            "items": bom["items"],
        }
    )
    doc = erp.submit(doc)
    print(f"  + BOM: {doc['name']} (cost materiale {doc['raw_material_cost']})")
    return doc["name"]


def ensure_user(erp, user):
    """Creează userul (dacă lipsește) și îi generează o pereche nouă de chei API."""
    if not erp.get("User", user["email"]):
        print(f"  + User: {user['email']}")
        doc = {
            "doctype": "User",
            "email": user["email"],
            "first_name": user["first_name"],
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in user["roles"]],
        }
        if os.environ.get("DEMO_PASSWORD"):
            doc["new_password"] = os.environ["DEMO_PASSWORD"]
        erp.insert(doc)
    keys = erp.call("frappe.core.doctype.user.user.generate_keys", user=user["email"])
    return ERP(erp.url, keys["api_key"], keys["api_secret"])


# ---------------------------------------------------------------- tranzacții


def payment(erp, dt, dn, ref):
    pe = erp.call(GET_PE, dt=dt, dn=dn)
    pe["reference_no"] = f"SEED-{ref}"  # obligatorii dacă contul e de tip Bank
    pe["reference_date"] = str(TODAY)
    return pe


def purchase(erp, state, tx, data):
    k = tx["id"]
    raw = data["warehouses"]["raw"]
    items = [{**i, "schedule_date": NEXT_WEEK, "warehouse": raw} for i in tx["items"]]
    print(f"{k}: achizitie {tx['supplier']}")

    if tx.get("material_request"):
        mr = step(
            erp,
            state,
            f"{k}.material_request",
            "Material Request",
            lambda: {
                "doctype": "Material Request",
                "material_request_type": "Purchase",
                "company": data["company"],
                "schedule_date": NEXT_WEEK,
                "items": items,
            },
        )

        def build_po():
            po = erp.call(MAKE_PO_FROM_MR, source_name=mr["name"])
            po["supplier"] = tx["supplier"]
            return po
    else:

        def build_po():
            return {
                "doctype": "Purchase Order",
                "supplier": tx["supplier"],
                "company": data["company"],
                "schedule_date": NEXT_WEEK,
                "set_warehouse": raw,
                "items": items,
            }

    po = step(erp, state, f"{k}.purchase_order", "Purchase Order", build_po)
    pr = step(erp, state, f"{k}.purchase_receipt", "Purchase Receipt",
        lambda: erp.call(MAKE_PR, source_name=po["name"]))
    pi = step(erp, state, f"{k}.purchase_invoice", "Purchase Invoice",
        lambda: erp.call(MAKE_PI, source_name=pr["name"]))
    if tx.get("pay"):
        step(erp, state, f"{k}.payment_entry", "Payment Entry",
            lambda: payment(erp, "Purchase Invoice", pi["name"], k))


def manufacture(erp, state, tx, data, bom):
    k = tx["id"]
    wh = data["warehouses"]
    print(f"{k}: productie {tx['qty']} x {tx['item']}")
    wo = step(
        erp,
        state,
        f"{k}.work_order",
        "Work Order",
        lambda: {
            "doctype": "Work Order",
            "production_item": tx["item"],
            "bom_no": bom,
            "qty": tx["qty"],
            "company": data["company"],
            "source_warehouse": wh["raw"],
            "wip_warehouse": wh["wip"],
            "fg_warehouse": wh["fg"],
        },
    )
    for purpose, key in (("Material Transfer for Manufacture", "transfer"), ("Manufacture", "manufacture")):
        step(erp, state, f"{k}.{key}", "Stock Entry",
            lambda purpose=purpose: erp.call(MAKE_SE, work_order_id=wo["name"], purpose=purpose, qty=tx["qty"]))


def confirm_sales_order(erp, so):
    """Din ziua 7 Sales Order are workflow: submit-ul se face prin acțiunea „Submit”."""
    return erp.call(APPLY_WORKFLOW, doc=so, action="Submit")


def sales_order_doc(tx, data):
    doc = {
        "doctype": "Sales Order",
        "customer": tx["customer"],
        "company": data["company"],
        "delivery_date": NEXT_WEEK,
        "set_warehouse": data["warehouses"]["fg"],
        "items": [{**i, "delivery_date": NEXT_WEEK} for i in tx["items"]],
    }
    if tx.get("installation_notes"):
        doc["installation_notes"] = tx["installation_notes"]
    return doc


def sale(erp, state, tx, data):
    k = tx["id"]
    print(f"{k}: vanzare {tx['customer']}")
    if tx.get("quotation"):
        qtn = step(
            erp,
            state,
            f"{k}.quotation",
            "Quotation",
            lambda: {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": tx["customer"],
                "company": data["company"],
                "items": tx["items"],
            },
        )

        def build_so():
            so = erp.call(MAKE_SO_FROM_QTN, source_name=qtn["name"])
            so["delivery_date"] = NEXT_WEEK
            so["set_warehouse"] = data["warehouses"]["fg"]
            for row in so["items"]:
                row["delivery_date"] = NEXT_WEEK
            if tx.get("installation_notes"):
                so["installation_notes"] = tx["installation_notes"]
            return so
    else:

        def build_so():
            return sales_order_doc(tx, data)

    so = step(erp, state, f"{k}.sales_order", "Sales Order", build_so,
        submit=lambda doc: confirm_sales_order(erp, doc))
    if not tx.get("deliver"):
        return
    dn = step(erp, state, f"{k}.delivery_note", "Delivery Note",
        lambda: erp.call(MAKE_DN, source_name=so["name"]))
    si = step(erp, state, f"{k}.sales_invoice", "Sales Invoice",
        lambda: erp.call(MAKE_SI, source_name=dn["name"]))
    if tx.get("pay"):
        step(erp, state, f"{k}.payment_entry", "Payment Entry",
            lambda: payment(erp, "Sales Invoice", si["name"], k))


def sale_with_approval(state, tx, data, sales, manager):
    """S3: creat și trimis la aprobare de Sales User, aprobat de Sales Manager."""
    k = tx["id"]
    print(f"{k}: vanzare cu aprobare {tx['customer']}")
    name = state.get(f"{k}.sales_order")
    so = sales.get("Sales Order", name) if name else None
    if not so or so["docstatus"] == 2:
        so = sales.insert(sales_order_doc(tx, data))
        state.set(f"{k}.sales_order", so["name"])
    if so["workflow_state"] == "Draft":
        so = sales.call(APPLY_WORKFLOW, doc=so, action="Send for Approval")
        print(f"  + {so['name']}: Draft -> {so['workflow_state']} (de {whoami(sales)})")
    if so["workflow_state"] == "Pending Approval":
        so = manager.call(APPLY_WORKFLOW, doc=so, action="Approve")
        print(f"  + {so['name']}: Pending Approval -> {so['workflow_state']} (de {whoami(manager)})")
    else:
        print(f"  = {so['name']}: {so['workflow_state']} (exista deja)")


# ---------------------------------------------------------------- verificare (secțiunea 3.7)


def report_rows(erp, report_name, filters):
    result = erp.call(RUN_REPORT, report_name=report_name, filters=filters, ignore_prepared_report=True)
    return [row for row in result["result"] if isinstance(row, dict)]


def verify(erp, state, data):
    company = data["company"]
    exp = data["expected"]
    ok = True

    def check(label, actual, expected):
        nonlocal ok
        good = abs(float(actual or 0) - float(expected)) < 0.01
        ok = ok and good
        print(f"  {'OK ' if good else 'NOK'}  {label:<48} asteptat {expected:>9}  obtinut {actual or 0:>9}")

    print("Verificare (sectiunea 3.7)")
    rows = report_rows(erp, "Stock Balance",
        {"company": company, "from_date": f"{TODAY.year}-01-01", "to_date": str(TODAY)})
    balance = {(r.get("item_code"), r.get("warehouse")): r.get("bal_qty") for r in rows}
    for line in exp["stock"]:
        check(f"Stoc {line['item_code']} @ {line['warehouse']}",
            balance.get((line["item_code"], line["warehouse"])), line["qty"])
    check(f"Stoc total @ {exp['empty_warehouse']}",
        sum(q or 0 for (_, w), q in balance.items() if w == exp["empty_warehouse"]), 0)

    common = {"company": company, "report_date": str(TODAY), "ageing_based_on": "Due Date",
        "range": "30, 60, 90, 120"}
    receivable = {}
    for r in report_rows(erp, "Accounts Receivable", {**common, "party_type": "Customer"}):
        if r.get("party"):
            receivable[r["party"]] = receivable.get(r["party"], 0) + (r.get("outstanding") or 0)
    for party, amount in exp["receivable"].items():
        check(f"De incasat de la {party}", receivable.get(party, 0), amount)
    payable = sum(r.get("outstanding") or 0
        for r in report_rows(erp, "Accounts Payable", {**common, "party_type": "Supplier"})
        if r.get("party"))
    check("De platit (toti furnizorii)", payable, exp["payable_total"])

    # Din ziua 7: cererea de instalare pentru S1 și comanda S3 aprobată prin workflow
    s1 = state.get("S1.sales_order")
    check(f"Installation Request pentru S1 ({s1})",
        len(erp.get_list("Installation Request", [["sales_order", "=", s1]])), 1)
    approved = exp["approved_order"]
    so = erp.get("Sales Order", state.get(f"{approved['id']}.sales_order"))
    check(f"{approved['id']} aprobat ({so['workflow_state']}), docstatus", so["docstatus"], 1)
    check(f"{approved['id']} valoare", so["grand_total"], approved["grand_total"])
    check(f"{approved['id']} livrat %", so["per_delivered"], 0)
    return ok


# ---------------------------------------------------------------- main


def load_env():
    """Mini-loader pentru scripts/.env (KEY=VALUE), fără dependențe în plus."""
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def main():
    load_env()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    erp = ERP(os.environ["ERP_URL"], os.environ["ERP_KEY"], os.environ["ERP_SECRET"])
    print(f"Site: {erp.url} (user {whoami(erp)})")
    state = State(erp, data["company"])

    bom = seed_master_data(erp, data)
    print("Useri")
    users = {role: ensure_user(erp, user) for role, user in data["users"].items()}

    for tx in data["transactions"]:
        if tx["type"] == "purchase":
            purchase(erp, state, tx, data)
        elif tx["type"] == "manufacture":
            manufacture(erp, state, tx, data, bom)
        elif tx["type"] == "sale":
            sale(erp, state, tx, data)
        elif tx["type"] == "sale_with_approval":
            sale_with_approval(state, tx, data, users["sales"], users["manager"])

    if not verify(erp, state, data):
        print("\nREZULTAT: valorile NU corespund cu sectiunea 3.7")
        sys.exit(1)
    print("\nREZULTAT: toate verificarile au trecut")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # mesajele serverului pot avea diacritice
    try:
        main()
    except ERPError as e:
        print(f"\nEROARE API: {e}")
        sys.exit(2)
