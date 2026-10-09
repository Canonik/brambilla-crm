"""Numbers: non-finite values are a 400, line totals use the migration's HALF_UP rounding,
and a line item without quantity (default 1) still gets its amount.

On a6e39d4 "Infinity" raised OverflowError (500), "NaN" was stored as a number, a line item
without quantity got quantity 1 but no amount, and 0.045 rounded to 0.04 through the API while
the migration rounds R4 line totals HALF_UP to 0.05.
"""
import pytest

from .conftest import H


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "inf", "nan"])
def test_non_finite_number_is_400(api, value):
    r = api.post("/crm/v3/objects/products", headers=H, json={"properties": {"name": "x", "price": value}})
    assert r.status_code == 400, r.text
    assert r.json()["category"] == "VALIDATION_ERROR"
    r = api.post("/crm/v3/objects/deals", headers=H, json={"properties": {"dealname": "x", "amount": value}})
    assert r.status_code == 400, r.text


def test_line_item_default_quantity_has_amount(api):
    r = api.post("/crm/v3/objects/line_items", headers=H, json={"properties": {"name": "Una unita", "price": "12.34"}})
    assert r.status_code == 201, r.text
    p = r.json()["properties"]
    assert p["quantity"] == "1" and p["amount"] == "12.34", p


def test_line_total_rounds_half_up_like_migration(api):
    r = api.post("/crm/v3/objects/line_items", headers=H, json={"properties": {"name": "Mezzo centesimo", "price": "0.05", "quantity": "1", "hs_discount_percentage": "10"}})
    assert r.status_code == 201, r.text
    assert r.json()["properties"]["amount"] == "0.05"


def test_line_total_follows_updates(api):
    li = api.post("/crm/v3/objects/line_items", headers=H, json={"properties": {"name": "Riga", "price": "10", "quantity": "3"}}).json()
    assert li["properties"]["amount"] == "30.00"
    r = api.patch(f"/crm/v3/objects/line_items/{li['id']}", headers=H, json={"properties": {"hs_discount_percentage": "15"}})
    assert r.json()["properties"]["amount"] == "25.50"
