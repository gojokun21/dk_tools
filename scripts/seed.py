import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "seed_data.json"

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

    bom = seed_master_data(erp, data)
    print(f"\nMaster data OK (BOM implicit: {bom})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # mesajele serverului pot avea diacritice
    try:
        main()
    except ERPError as e:
        print(f"\nEROARE API: {e}")
        sys.exit(2)
