import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "database.db"
    monkeypatch.setattr(app_module, "DATABASE", str(database_path))
    app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app_module.app.test_client() as test_client:
        with app_module.app.app_context():
            app_module.init_db()
        yield test_client


def test_catalog_is_seeded_and_pages_load(client):
    response = client.get("/")
    assert response.status_code == 200

    with app_module.app.app_context():
        rows = app_module.get_db().execute("SELECT item_name, default_price FROM item_catalog").fetchall()

    catalog = {row["item_name"]: row["default_price"] for row in rows}
    assert catalog["Rádio"] == 500
    assert catalog["Tazer"] == 3000
    assert catalog["Chladící obklad"] == 1


def test_shift_lifecycle_creates_message_and_redirects_to_edit(client):
    first_start = client.post(
        "/shifts/start",
        data={"name": "Tommy Miler", "callsign": "Angel-1", "note": "test"},
        follow_redirects=True,
    )
    assert first_start.status_code == 200

    second_start = client.post(
        "/shifts/start",
        data={"name": "Other", "callsign": "Angel-2"},
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
            "item_note[]": ["", ""],
        },
        follow_redirects=True,
    )
    assert purchase.status_code == 200

    end_response = client.post("/shifts/end")
    assert end_response.status_code == 200
    payload = end_response.get_json()
    assert payload["ok"] is True
    assert payload["redirect_url"].endswith("/edit")
    assert "## Zápis směny" in payload["message"]
    assert "**SPZ / použitá vozidla:** neuvedeno" in payload["message"]
    assert "- 10x Defibrilátor | $100" in payload["message"]
    assert "**Celková cena:** $200" in payload["message"]

    second_end = client.post("/shifts/end")
    assert second_end.status_code == 400
    assert second_end.get_json()["ok"] is False


def test_finished_shift_can_be_edited_and_duration_is_recalculated(client):
    client.post(
        "/shifts/start",
        data={"name": "Taylor Green", "callsign": "Angel-7", "note": "původní"},
        follow_redirects=True,
    )
    client.post("/shifts/end")

    with app_module.app.app_context():
        shift_id = app_module.get_db().execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()["id"]

    response = client.post(
        f"/shifts/{shift_id}/edit",
        data={
            "name": "Taylor Green",
            "callsign": "Angel-7",
            "started_at": "2026-06-20T10:00",
            "ended_at": "2026-06-20T12:45",
            "vehicle": "EMS-12\nEMS-41",
            "note": "upraveno",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Směna byla upravena" in response.get_data(as_text=True)

    with app_module.app.app_context():
        shift = app_module.get_db().execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()

    assert shift["shift_date"] == "2026-06-20"
    assert shift["duration_minutes"] == 165
    assert app_module.format_vehicle_text(shift["vehicle"]) == "EMS-12, EMS-41"
    assert "**Čas směny:** 10:00 - 12:45" in shift["discord_message"]
    assert "**Délka směny:** 2 h 45 min" in shift["discord_message"]
    assert "**SPZ / použitá vozidla:** EMS-12, EMS-41" in shift["discord_message"]


def test_purchase_edit_without_active_shift_updates_related_shift_message(client):
    client.post(
        "/shifts/start",
        data={"name": "Thomas Black", "callsign": "T-16"},
        follow_redirects=True,
    )
    client.post(
        "/purchases/add",
        data={
            "name": "Thomas Black",
            "callsign": "T-16",
            "reason": "Výbava",
            "item_name[]": ["Medibag"],
            "quantity[]": ["1"],
            "unit_price[]": ["10"],
            "item_note[]": [""],
        },
        follow_redirects=True,
    )
    client.post("/shifts/end")

    with app_module.app.app_context():
        db = app_module.get_db()
        purchase_id = db.execute("SELECT id FROM purchases ORDER BY id DESC LIMIT 1").fetchone()["id"]
        shift_id = db.execute("SELECT id FROM shifts ORDER BY id DESC LIMIT 1").fetchone()["id"]

    response = client.post(
        f"/purchases/{purchase_id}/edit",
        data={
            "name": "Thomas Black",
            "callsign": "T-16",
            "reason": "Doplnění skladu",
            "note": "upraveno",
            "item_name[]": ["Medibag"],
            "quantity[]": ["3"],
            "unit_price[]": ["10"],
            "item_note[]": ["po směně"],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Nákup byl úspěšně upraven" in response.get_data(as_text=True)

    with app_module.app.app_context():
        db = app_module.get_db()
        purchase = db.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
        shift = db.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()

    assert purchase["total_price"] == 30
    assert purchase["discord_message"] is not None
    assert "- 3x Medibag | $30" in shift["discord_message"]
    assert "**Celková cena:** $30" in shift["discord_message"]


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
            "item_note[]": [""],
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
            "item_note[]": [""],
        },
        follow_redirects=True,
    )
    assert confirmed.status_code == 200
    assert "Nákup byl úspěšně přidán" in confirmed.get_data(as_text=True)
