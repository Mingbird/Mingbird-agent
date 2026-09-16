"""Failing tests for the wf04 buggy fixture. The agent must make these pass
WITHOUT modifying this file."""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from inventory import add_item, remove_item, total_value, search


@pytest.fixture
def db():
    d = {}
    add_item(d, "A1", "hex bolt M8", 100, 0.15)
    add_item(d, "B2", "Hex Nut M8", 200, 0.05)
    return d


def test_add_and_load(db, tmp_path):
    p = tmp_path / "db.json"
    save_ok = json.dump(db, open(p, "w"))
    from inventory import load_db
    loaded = load_db(str(p))
    assert loaded["A1"]["qty"] == 100


def test_add_existing_sku_raises(db):
    with pytest.raises(ValueError):
        add_item(db, "A1", "duplicate", 1, 1.0)


def test_remove_to_zero_deletes(db):
    remove_item(db, "A1", 100)
    assert "A1" not in db


def test_remove_prevents_negative(db):
    with pytest.raises(ValueError):
        remove_item(db, "A1", 500)


def test_total_value_counts_quantity(db):
    assert total_value(db) == pytest.approx(100 * 0.15 + 200 * 0.05)


def test_search_case_insensitive(db):
    assert "B2" in search(db, "hex nut")
    assert "A1" in search(db, "HEX")
