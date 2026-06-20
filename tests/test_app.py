import os

import pytest

import app as app_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "database.db"
    monkeypatch.setattr(app_module, "DATABASE", str(database_path))
    app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app_module.app.test_client() as test_client:
        yield test_client


def test_catalog_is_seeded_and_pages_load(client):
    response = client.get("/")
    assert response.status_code == 200

    with app_module.app.app_context():
        app_module.init_db()
        rows = app_module.get_db().execute("SELECT item_name, default_price, weight_grams FROM item_catalog").fetchall()

    catalog = {row["item_name"]: (row["default_price"], row["weight_grams"]) for row in rows}
    assert catalog["Rádio"] == (500, 100)
    assert catalog["Tazer"] == (3000, 227)
    assert catalog["Chladící obklad"] == (1, 200)


def test_shift_lifecycle_prevents_second_active_shift_and_creates_discord_message(client):
    first_start = client.post(
        "/shifts/start",
        data={"name": "Tommy Miler", "callsign": "Angel-1", "vehicle": "ABC 123", "note": "test"},
        follow_redirects=True,
    )
    assert first_start.status_code == 200

    second_start = client.post(
        "/shifts/start",
        data={"name": "Other", "callsign": "Angel-2", "vehicle": "XYZ 999"},
        follow_redirects=True,
    )
    assert "Nelze zahájit druhou směnu" in second_start.get_data(as_text=True)

    purchase = client.post(
        "/purchases/add",
        data={
            "name": "Tommy Miler",
            "callsign": "Angel-1",
            "reason": "Výbava",
            "note": "",
            "item_name[]": ["Defibrilátor", "Bandáže"],
            "quantity[]": ["10", "10"],
            "unit_price[]": ["10", "10"],
            "weight_grams[]": ["100", "100"],
            "item_note[]": ["", ""],
        },
        follow_redirects=True,
    )
    assert purchase.status_code == 200

    end_response = client.post("/shifts/end")
    assert end_response.status_code == 200
    payload = end_response.get_json()
    assert payload["ok"] is True
    assert "## Zápis směny" in payload["message"]
    assert "- 10x Defibrilátor | $100 | 1000g" in payload["message"]
    assert "**Celková cena:** $200" in payload["message"]

    second_end = client.post("/shifts/end")
    assert second_end.status_code == 400
    assert second_end.get_json()["ok"] is False


def test_purchase_without_active_shift_requires_confirmation(client):
    response = client.post(
        "/purchases/add",
        data={
            "name": "Thomas Black",
            "callsign": "T-16",
            "reason": "Výbava",
            "item_name[]": ["Medibag"],
            "quantity[]": ["1"],
            "unit_price[]": ["10"],
            "weight_grams[]": ["220"],
        },
    )
    assert response.status_code == 200
    assert "Není aktivní směna" in response.get_data(as_text=True)

    confirmed = client.post(
        "/purchases/add",
        data={
            "allow_without_shift": "1",
            "name": "Thomas Black",
            "callsign": "T-16",
            "reason": "Výbava",
            "item_name[]": ["Medibag"],
            "quantity[]": ["1"],
            "unit_price[]": ["10"],
            "weight_grams[]": ["220"],
        },
        follow_redirects=True,
    )
    assert confirmed.status_code == 200
    assert "Nákup byl úspěšně přidán" in confirmed.get_data(as_text=True)
