import csv
import io
import os
import sqlite3
from datetime import datetime

from flask import Flask, Response, flash, g, redirect, render_template, request, url_for


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "instance", "database.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "zmente-tento-lokalni-klic"


def get_db():
    """Return a SQLite connection stored for the current request."""
    if "db" not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    """Close the request database connection."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create application tables when they do not exist yet."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            callsign TEXT NOT NULL,
            shift_date TEXT NOT NULL,
            time_from TEXT NOT NULL,
            time_to TEXT NOT NULL,
            vehicle TEXT NOT NULL,
            duration_hours REAL NOT NULL DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            callsign TEXT NOT NULL,
            reason TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'ks',
            note TEXT,
            FOREIGN KEY (purchase_id) REFERENCES purchases (id) ON DELETE CASCADE
        );
        """
    )
    db.commit()


def calculate_duration(time_from, time_to):
    """Calculate shift length in hours, or return None for invalid input."""
    try:
        start = datetime.strptime(time_from, "%H:%M")
        end = datetime.strptime(time_to, "%H:%M")
    except (TypeError, ValueError):
        return None

    if end <= start:
        return None

    seconds = (end - start).total_seconds()
    return round(seconds / 3600, 2)


def current_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_purchase_items(purchase_id):
    return get_db().execute(
        "SELECT * FROM purchase_items WHERE purchase_id = ? ORDER BY id", (purchase_id,)
    ).fetchall()


@app.before_request
def ensure_database():
    init_db()


@app.route("/")
def dashboard():
    db = get_db()
    shift_count = db.execute("SELECT COUNT(*) AS count FROM shifts").fetchone()["count"]
    purchase_count = db.execute("SELECT COUNT(*) AS count FROM purchases").fetchone()["count"]
    total_hours = db.execute("SELECT COALESCE(SUM(duration_hours), 0) AS total FROM shifts").fetchone()["total"]
    latest_shifts = db.execute("SELECT * FROM shifts ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
    latest_purchases = db.execute("SELECT * FROM purchases ORDER BY created_at DESC, id DESC LIMIT 5").fetchall()
    return render_template(
        "dashboard.html",
        shift_count=shift_count,
        purchase_count=purchase_count,
        total_hours=round(total_hours, 2),
        latest_shifts=latest_shifts,
        latest_purchases=latest_purchases,
    )


@app.route("/shifts")
def shifts():
    query = request.args.get("q", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    sql = "SELECT * FROM shifts WHERE 1=1"
    params = []
    if query:
        sql += " AND (name LIKE ? OR callsign LIKE ? OR vehicle LIKE ?)"
        like_query = f"%{query}%"
        params.extend([like_query, like_query, like_query])
    if date_from:
        sql += " AND shift_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND shift_date <= ?"
        params.append(date_to)
    sql += " ORDER BY shift_date DESC, time_from DESC, id DESC"

    records = get_db().execute(sql, params).fetchall()
    return render_template("shifts.html", shifts=records, query=query, date_from=date_from, date_to=date_to)


@app.route("/shifts/add", methods=["GET", "POST"])
def add_shift():
    return handle_shift_form()


@app.route("/shifts/<int:shift_id>/edit", methods=["GET", "POST"])
def edit_shift(shift_id):
    shift = get_db().execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if shift is None:
        flash("Směna nebyla nalezena.", "danger")
        return redirect(url_for("shifts"))
    return handle_shift_form(shift)


def handle_shift_form(shift=None):
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        callsign = request.form.get("callsign", "").strip()
        shift_date = request.form.get("shift_date", "").strip()
        time_from = request.form.get("time_from", "").strip()
        time_to = request.form.get("time_to", "").strip()
        vehicle = request.form.get("vehicle", "").strip()
        note = request.form.get("note", "").strip()
        duration = calculate_duration(time_from, time_to)

        if not all([name, callsign, shift_date, time_from, time_to, vehicle]):
            flash("Vyplňte všechna povinná pole směny.", "danger")
        elif duration is None:
            flash("Čas do musí být větší než čas od.", "danger")
        else:
            db = get_db()
            if shift is None:
                db.execute(
                    """
                    INSERT INTO shifts (name, callsign, shift_date, time_from, time_to, vehicle, duration_hours, note, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, callsign, shift_date, time_from, time_to, vehicle, duration, note, current_timestamp()),
                )
                flash("Směna byla úspěšně přidána.", "success")
            else:
                db.execute(
                    """
                    UPDATE shifts
                    SET name = ?, callsign = ?, shift_date = ?, time_from = ?, time_to = ?, vehicle = ?, duration_hours = ?, note = ?
                    WHERE id = ?
                    """,
                    (name, callsign, shift_date, time_from, time_to, vehicle, duration, note, shift["id"]),
                )
                flash("Směna byla úspěšně upravena.", "success")
            db.commit()
            return redirect(url_for("shifts"))

    return render_template("shift_form.html", shift=shift)


@app.route("/shifts/<int:shift_id>/delete", methods=["POST"])
def delete_shift(shift_id):
    db = get_db()
    db.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
    db.commit()
    flash("Směna byla smazána.", "success")
    return redirect(url_for("shifts"))


@app.route("/shifts/export")
def export_shifts():
    rows = get_db().execute("SELECT * FROM shifts ORDER BY shift_date DESC, time_from DESC").fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Jméno", "Volací znak", "Datum", "Čas od", "Čas do", "Vozidlo", "Hodiny", "Poznámka", "Vytvořeno"])
    for row in rows:
        writer.writerow([row["id"], row["name"], row["callsign"], row["shift_date"], row["time_from"], row["time_to"], row["vehicle"], row["duration_hours"], row["note"] or "", row["created_at"]])
    return csv_response(output.getvalue(), "smeny.csv")


@app.route("/purchases")
def purchases():
    query = request.args.get("q", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    sql = """
        SELECT DISTINCT p.*
        FROM purchases p
        LEFT JOIN purchase_items i ON i.purchase_id = p.id
        WHERE 1=1
    """
    params = []
    if query:
        sql += " AND (p.name LIKE ? OR p.callsign LIKE ? OR i.item_name LIKE ?)"
        like_query = f"%{query}%"
        params.extend([like_query, like_query, like_query])
    if date_from:
        sql += " AND date(p.created_at) >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND date(p.created_at) <= ?"
        params.append(date_to)
    sql += " ORDER BY p.created_at DESC, p.id DESC"

    records = get_db().execute(sql, params).fetchall()
    items_by_purchase = {record["id"]: fetch_purchase_items(record["id"]) for record in records}
    return render_template("purchases.html", purchases=records, items_by_purchase=items_by_purchase, query=query, date_from=date_from, date_to=date_to)


@app.route("/purchases/add", methods=["GET", "POST"])
def add_purchase():
    return handle_purchase_form()


@app.route("/purchases/<int:purchase_id>/edit", methods=["GET", "POST"])
def edit_purchase(purchase_id):
    purchase = get_db().execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
    if purchase is None:
        flash("Nákup nebyl nalezen.", "danger")
        return redirect(url_for("purchases"))
    items = fetch_purchase_items(purchase_id)
    return handle_purchase_form(purchase, items)


def parse_items(form):
    names = form.getlist("item_name[]")
    quantities = form.getlist("quantity[]")
    units = form.getlist("unit[]")
    notes = form.getlist("item_note[]")
    items = []
    for index, item_name in enumerate(names):
        item_name = item_name.strip()
        if not item_name:
            continue
        try:
            quantity = float(quantities[index] or 1)
        except (IndexError, ValueError):
            quantity = 1
        unit = units[index].strip() if index < len(units) and units[index].strip() else "ks"
        note = notes[index].strip() if index < len(notes) else ""
        items.append({"item_name": item_name, "quantity": quantity, "unit": unit, "note": note})
    return items


def handle_purchase_form(purchase=None, items=None):
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        callsign = request.form.get("callsign", "").strip()
        reason = request.form.get("reason", "").strip()
        note = request.form.get("note", "").strip()
        parsed_items = parse_items(request.form)

        if not all([name, callsign, reason]):
            flash("Vyplňte všechna povinná pole nákupu.", "danger")
        elif not parsed_items:
            flash("Přidejte alespoň jednu položku nákupu.", "danger")
        else:
            db = get_db()
            if purchase is None:
                cursor = db.execute(
                    "INSERT INTO purchases (name, callsign, reason, note, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, callsign, reason, note, current_timestamp()),
                )
                purchase_id = cursor.lastrowid
                flash("Nákup byl úspěšně přidán.", "success")
            else:
                purchase_id = purchase["id"]
                db.execute(
                    "UPDATE purchases SET name = ?, callsign = ?, reason = ?, note = ? WHERE id = ?",
                    (name, callsign, reason, note, purchase_id),
                )
                db.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (purchase_id,))
                flash("Nákup byl úspěšně upraven.", "success")

            for item in parsed_items:
                db.execute(
                    "INSERT INTO purchase_items (purchase_id, item_name, quantity, unit, note) VALUES (?, ?, ?, ?, ?)",
                    (purchase_id, item["item_name"], item["quantity"], item["unit"], item["note"]),
                )
            db.commit()
            return redirect(url_for("purchases"))

    if items is None:
        items = []
    return render_template("purchase_form.html", purchase=purchase, items=items)


@app.route("/purchases/<int:purchase_id>/delete", methods=["POST"])
def delete_purchase(purchase_id):
    db = get_db()
    db.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (purchase_id,))
    db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
    db.commit()
    flash("Nákup byl smazán.", "success")
    return redirect(url_for("purchases"))


@app.route("/purchases/export")
def export_purchases():
    rows = get_db().execute(
        """
        SELECT p.id, p.name, p.callsign, p.reason, p.note AS purchase_note, p.created_at,
               i.item_name, i.quantity, i.unit, i.note AS item_note
        FROM purchases p
        LEFT JOIN purchase_items i ON i.purchase_id = p.id
        ORDER BY p.created_at DESC, p.id DESC, i.id ASC
        """
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID nákupu", "Jméno", "Volací znak", "Důvod", "Poznámka nákupu", "Vytvořeno", "Položka", "Množství", "Jednotka", "Poznámka položky"])
    for row in rows:
        writer.writerow([row["id"], row["name"], row["callsign"], row["reason"], row["purchase_note"] or "", row["created_at"], row["item_name"] or "", row["quantity"] or "", row["unit"] or "", row["item_note"] or ""])
    return csv_response(output.getvalue(), "nakupy.csv")


def csv_response(content, filename):
    return Response(
        "\ufeff" + content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
