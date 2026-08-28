"""Inventory management module (buggy). Part of the wf04 fixture project."""
import json
import os

DB_PATH = "inventory.json"


def load_db(path=DB_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db, path=DB_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)


def add_item(db, sku, name, qty, price):
    """Add a new item. BUG-1: silently overwrites existing SKU instead of raising."""
    db[sku] = {"name": name, "qty": qty, "price": price}
    return db


def remove_item(db, sku, quantity=1):
    """Remove `quantity` units of an item. BUG-2: never deletes the SKU when qty reaches 0,
    leaving zero-quantity ghost entries; also allows negative stock."""
    if sku not in db:
        raise KeyError(sku)
    db[sku]["qty"] -= quantity
    return db


def total_value(db):
    """Total stock value. BUG-3: uses string price if price was stored as str,
    causing TypeError for mixed-type inputs; ignores qty."""
    return sum(item["price"] for item in db.values())


def search(db, term):
    """Case-sensitive search. BUG-4: search is case sensitive, spec requires case-insensitive."""
    return {sku: it for sku, it in db.items() if term in it["name"]}
