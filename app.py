import csv
import io
import os
import sqlite3
from datetime import datetime

from flask import Flask, Response, flash, g, jsonify, redirect, render_template, request, url_for


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "instance", "database.db")
CATALOG_ITEMS = [
    ("Rádio", 500),
    ("Tazer", 3000),
    ("Medibag", 10),
    ("Bandáže", 10),
    ("Defibrilátor", 10),
    ("Pinzeta", 10),
    ("Krém na popálení", 10),
    ("Šicí souprava", 10),
    ("Chladící obklad", 1),
]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("TRINITY_SECRET_KEY", "zmente-tento-lokalni-klic")


def get_db():
    """Return a SQLite connection stored for the current request."""
    if "db" not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables and seed the item catalog on first run."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            callsign TEXT NOT NULL,
            vehicle TEXT NOT NULL,
            shift_date TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_minutes INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'probíhá',
            note TEXT,
            discord_message TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id INTEGER,
            name TEXT NOT NULL,
            callsign TEXT NOT NULL,
            reason TEXT NOT NULL,
            note TEXT,
            total_price REAL NOT NULL DEFAULT 0,
            discord_message TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (shift_id) REFERENCES shifts (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            note TEXT,
            FOREIGN KEY (purchase_id) REFERENCES purchases (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS item_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL UNIQUE,
            default_price REAL NOT NULL DEFAULT 0
        );
        """
    )
    ensure_columns(db)
    for catalog_item in CATALOG_ITEMS:
        item_name, default_price = catalog_item[:2]
        db.execute(
            """
            INSERT INTO item_catalog (item_name, default_price)
            VALUES (?, ?)
            ON CONFLICT(item_name) DO UPDATE SET default_price = excluded.default_price
            """,
            (item_name, default_price),
        )
    db.commit()


def ensure_columns(db):
    """Add new columns when an older local database already exists."""
    required = {
        "shifts": {
            "vehicle": "TEXT NOT NULL DEFAULT ''",
            "started_at": "TEXT",
            "ended_at": "TEXT",
            "duration_minutes": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'ukončeno'",
            "discord_message": "TEXT",
        },
        "purchases": {
            "shift_id": "INTEGER",
            "total_price": "REAL NOT NULL DEFAULT 0",
            "discord_message": "TEXT",
        },
        "purchase_items": {
            "unit_price": "REAL NOT NULL DEFAULT 0",
            "total_price": "REAL NOT NULL DEFAULT 0",
        },
    }
    for table, columns in required.items():
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@app.before_request
def ensure_database():
    init_db()


@app.context_processor
def inject_active_shift():
    return {"active_shift": get_active_shift()}


def now_dt():
    return datetime.now()


def db_timestamp(value=None):
    return (value or now_dt()).strftime("%Y-%m-%d %H:%M:%S")


def date_for_input(value):
    if not value:
        return ""
    return value[:10]


def datetime_for_input(value):
    parsed = parse_db_datetime(value)
    return parsed.strftime("%Y-%m-%dT%H:%M") if parsed else ""


def get_active_shift():
    return get_db().execute(
        "SELECT * FROM shifts WHERE status = 'probíhá' ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()


def get_catalog():
    return get_db().execute("SELECT * FROM item_catalog ORDER BY item_name").fetchall()


def parse_db_datetime(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def parse_form_datetime(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def format_time(value):
    parsed = parse_db_datetime(value)
    return parsed.strftime("%H:%M") if parsed else ""


def format_date_cz(value):
    parsed = parse_db_datetime(value) if len(value or "") > 10 else datetime.strptime(value, "%Y-%m-%d")
    return f"{parsed.day}. {parsed.month}. {parsed.year}"


def format_duration(minutes):
    minutes = int(minutes or 0)
    hours = minutes // 60
    rest = minutes % 60
    if hours and rest:
        return f"{hours} h {rest} min"
    if hours:
        return f"{hours} hodin"
    return f"{rest} min"


def calculate_minutes(started_at, ended_at):
    start = parse_db_datetime(started_at)
    end = parse_db_datetime(ended_at)
    if not start or not end or end <= start:
        return 0
    return int(round((end - start).total_seconds() / 60))


def fetch_purchase_items(purchase_id):
    return get_db().execute(
        "SELECT * FROM purchase_items WHERE purchase_id = ? ORDER BY id", (purchase_id,)
    ).fetchall()


def fetch_shift_purchases(shift_id):
    return get_db().execute(
        "SELECT * FROM purchases WHERE shift_id = ? ORDER BY created_at ASC, id ASC", (shift_id,)
    ).fetchall()


def build_purchase_message(purchase, items):
    lines = [
        "## Zápis nákupu",
        "",
        f"**Jméno:** {purchase['name']}",
        f"**Volací znak:** {purchase['callsign']}",
        f"**Důvod:** {purchase['reason']}",
        "",
        "### Položky",
    ]
    for item in items:
        lines.append(
            f"- {format_quantity(item['quantity'])}x {item['item_name']} | ${format_money(item['total_price'])}"
        )
    lines.extend([
        "",
        f"**Celková cena:** ${format_money(purchase['total_price'])}",
        "",
        f"**Poznámka:** {purchase['note'] or 'bez poznámky'}",
    ])
    return "\n".join(lines)


def build_shift_message(shift):
    purchases = fetch_shift_purchases(shift["id"])
    total_price = sum(float(row["total_price"] or 0) for row in purchases)
    lines = [
        "## Zápis směny",
        "",
        f"**Jméno:** {shift['name']}",
        f"**Volací znak:** {shift['callsign']}",
        f"**Datum:** {format_date_cz(shift['shift_date'])}",
        f"**Čas směny:** {format_time(shift['started_at'])} - {format_time(shift['ended_at'])}",
        f"**Délka směny:** {format_duration(shift['duration_minutes'])}",
        f"**SPZ / použitá vozidla:** {format_vehicle_text(shift['vehicle'])}",
        "",
        "### Nákupy během směny",
    ]
    if purchases:
        for purchase in purchases:
            for item in fetch_purchase_items(purchase["id"]):
                lines.append(
                    f"- {format_quantity(item['quantity'])}x {item['item_name']} | ${format_money(item['total_price'])}"
                )
    else:
        lines.append("- žádné nákupy")
    lines.extend([
        "",
        f"**Celková cena:** ${format_money(total_price)}",
        "",
        f"**Poznámka:** {shift['note'] or 'bez poznámky'}",
    ])
    return "\n".join(lines)


def format_money(value):
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:.2f}"


def format_quantity(value):
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:.2f}"


def format_vehicle_text(value):
    parts = [line.strip() for line in (value or "").replace("\r", "\n").split("\n") if line.strip()]
    return ", ".join(parts) if parts else "neuvedeno"


def sync_purchase_message(purchase_id):
    purchase = get_db().execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
    if purchase is None:
        return None
    discord_message = build_purchase_message(purchase, fetch_purchase_items(purchase_id))
    get_db().execute("UPDATE purchases SET discord_message = ? WHERE id = ?", (discord_message, purchase_id))
    return get_db().execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()


def sync_shift_record(shift_id):
    shift = get_db().execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if shift is None:
        return None
    started = parse_db_datetime(shift["started_at"])
    shift_date = started.strftime("%Y-%m-%d") if started else shift["shift_date"]
    is_finished = bool(shift["ended_at"])
    duration_minutes = calculate_minutes(shift["started_at"], shift["ended_at"]) if is_finished else 0
    status = "ukončeno" if is_finished else "probíhá"
    get_db().execute(
        "UPDATE shifts SET shift_date = ?, duration_minutes = ?, status = ? WHERE id = ?",
        (shift_date, duration_minutes, status, shift_id),
    )
    shift = get_db().execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    discord_message = build_shift_message(shift) if is_finished else None
    get_db().execute("UPDATE shifts SET discord_message = ? WHERE id = ?", (discord_message, shift_id))
    return get_db().execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()





@app.route("/")
def dashboard():
    db = get_db()
    active_shift = get_active_shift()
    shift_count = db.execute("SELECT COUNT(*) AS count FROM shifts").fetchone()["count"]
    purchase_count = db.execute("SELECT COUNT(*) AS count FROM purchases").fetchone()["count"]
    total_minutes = db.execute("SELECT COALESCE(SUM(duration_minutes), 0) AS total FROM shifts").fetchone()["total"]
    latest_purchases = db.execute("SELECT * FROM purchases ORDER BY created_at DESC, id DESC LIMIT 6").fetchall()
    active_stats = {"count": 0, "total_price": 0}
    if active_shift:
        stats = db.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(total_price), 0) AS total_price FROM purchases WHERE shift_id = ?",
            (active_shift["id"],),
        ).fetchone()
        active_stats = dict(stats)
    return render_template(
        "dashboard.html",
        shift_count=shift_count,
        purchase_count=purchase_count,
        total_hours=round((total_minutes or 0) / 60, 2),
        latest_purchases=latest_purchases,
        active_stats=active_stats,
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
    sql += " ORDER BY started_at DESC, id DESC"
    records = get_db().execute(sql, params).fetchall()
    return render_template("shifts.html", shifts=records, query=query, date_from=date_from, date_to=date_to)


@app.route("/shifts/start", methods=["POST"])
def start_shift():
    if get_active_shift():
        flash("Nelze zahájit druhou směnu, jedna směna už probíhá.", "danger")
        return redirect(request.referrer or url_for("dashboard"))
    name = request.form.get("name", "").strip()
    callsign = request.form.get("callsign", "").strip()
    vehicle = request.form.get("vehicle", "").strip()
    note = request.form.get("note", "").strip()
    if not all([name, callsign]):
        flash("Pro zahájení směny vyplňte jméno a volací znak.", "danger")
        return redirect(request.referrer or url_for("dashboard"))
    started = now_dt()
    db = get_db()
    db.execute(
        """
        INSERT INTO shifts (name, callsign, vehicle, shift_date, started_at, status, note, created_at)
        VALUES (?, ?, ?, ?, ?, 'probíhá', ?, ?)
        """,
        (name, callsign, vehicle, started.strftime("%Y-%m-%d"), db_timestamp(started), note, db_timestamp(started)),
    )
    db.commit()
    flash("Směna byla zahájena. SPZ nebo použitá vozidla můžeš doplnit po směně.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/shifts/end", methods=["POST"])
def end_shift():
    active_shift = get_active_shift()
    if not active_shift:
        return jsonify({"ok": False, "message": "Žádná směna neběží."}), 400
    ended = now_dt()
    ended_at = db_timestamp(ended)
    duration_minutes = calculate_minutes(active_shift["started_at"], ended_at)
    db = get_db()
    db.execute(
        "UPDATE shifts SET ended_at = ?, duration_minutes = ?, status = 'ukončeno' WHERE id = ?",
        (ended_at, duration_minutes, active_shift["id"]),
    )
    finished_shift = sync_shift_record(active_shift["id"])
    db.commit()
    return jsonify(
        {
            "ok": True,
            "message": finished_shift["discord_message"],
            "redirect_url": url_for("edit_shift", shift_id=active_shift["id"]),
        }
    )


@app.route("/shifts/<int:shift_id>/edit", methods=["GET", "POST"])
def edit_shift(shift_id):
    shift = get_db().execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if shift is None:
        flash("Směna nebyla nalezena.", "danger")
        return redirect(url_for("shifts"))
    is_active_shift = shift["status"] == "probíhá"
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        callsign = request.form.get("callsign", "").strip()
        vehicle = request.form.get("vehicle", "").strip()
        note = request.form.get("note", "").strip()
        started = parse_form_datetime(request.form.get("started_at"))
        ended = parse_form_datetime(request.form.get("ended_at"))
        if not all([name, callsign, started]):
            flash("Vyplňte jméno, volací znak a platný začátek směny.", "danger")
        elif not is_active_shift and ended is None:
            flash("U ukončené směny vyplňte i platný konec směny.", "danger")
        elif ended and ended <= started:
            flash("Konec směny musí být později než začátek směny.", "danger")
        else:
            started_at = db_timestamp(started)
            ended_at = None if is_active_shift else db_timestamp(ended)
            db = get_db()
            db.execute(
                """
                UPDATE shifts
                SET name = ?, callsign = ?, vehicle = ?, note = ?, started_at = ?, ended_at = ?
                WHERE id = ?
                """,
                (name, callsign, vehicle, note, started_at, ended_at, shift_id),
            )
            sync_shift_record(shift_id)
            db.commit()
            flash("Směna byla upravena. Délka i zápis směny byly přepočítány.", "success")
            return redirect(url_for("shifts"))
    return render_template("shift_form.html", shift=shift, is_active_shift=is_active_shift)


@app.route("/shifts/<int:shift_id>/delete", methods=["POST"])
def delete_shift(shift_id):
    db = get_db()
    db.execute("UPDATE purchases SET shift_id = NULL WHERE shift_id = ?", (shift_id,))
    db.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
    db.commit()
    flash("Směna byla smazána.", "success")
    return redirect(url_for("shifts"))


@app.route("/shifts/export")
def export_shifts():
    rows = get_db().execute("SELECT * FROM shifts ORDER BY started_at DESC").fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Jméno", "Volací znak", "SPZ / vozidla", "Datum", "Začátek", "Konec", "Minuty", "Stav", "Poznámka", "Discord zpráva", "Vytvořeno"])
    for row in rows:
        writer.writerow([row["id"], row["name"], row["callsign"], row["vehicle"], row["shift_date"], row["started_at"], row["ended_at"] or "", row["duration_minutes"], row["status"], row["note"] or "", row["discord_message"] or "", row["created_at"]])
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
    return handle_purchase_form(purchase, fetch_purchase_items(purchase_id))


def parse_items(form):
    names = form.getlist("item_name[]")
    quantities = form.getlist("quantity[]")
    prices = form.getlist("unit_price[]")
    notes = form.getlist("item_note[]")
    items = []
    catalog = {row["item_name"]: row for row in get_catalog()}
    for index, item_name in enumerate(names):
        item_name = item_name.strip()
        if not item_name:
            continue
        catalog_item = catalog.get(item_name)
        quantity = parse_float(quantities[index] if index < len(quantities) else "1", 1)
        unit_price = parse_float(prices[index] if index < len(prices) else "", catalog_item["default_price"] if catalog_item else 0)
        quantity = max(quantity, 0.01)
        total_price = round(quantity * unit_price, 2)
        note = notes[index].strip() if index < len(notes) else ""
        items.append({"item_name": item_name, "quantity": quantity, "unit_price": unit_price, "total_price": total_price, "note": note})
    return items


def parse_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default or 0)


def handle_purchase_form(purchase=None, items=None):
    active_shift = get_active_shift()
    if request.method == "POST":
        allow_without_shift = request.form.get("allow_without_shift") == "1"
        needs_shift_confirmation = purchase is None and active_shift is None and not allow_without_shift
        if needs_shift_confirmation:
            flash("Není aktivní směna. Potvrďte uložení bez směny, nebo nejdříve zahajte směnu.", "danger")
            return render_template("purchase_form.html", purchase=purchase, items=items or [], catalog=get_catalog(), needs_shift_confirmation=True)
        default_name = active_shift["name"] if active_shift else ""
        default_callsign = active_shift["callsign"] if active_shift else ""
        name = request.form.get("name", default_name).strip() or default_name
        callsign = request.form.get("callsign", default_callsign).strip() or default_callsign
        reason = request.form.get("reason", "").strip()
        note = request.form.get("note", "").strip()
        parsed_items = parse_items(request.form)
        if not all([name, callsign, reason]):
            flash("Vyplňte jméno, volací znak a důvod nákupu.", "danger")
        elif not parsed_items:
            flash("Přidejte alespoň jednu položku nákupu.", "danger")
        else:
            total_price = round(sum(item["total_price"] for item in parsed_items), 2)
            shift_id = active_shift["id"] if active_shift else None
            db = get_db()
            if purchase is None:
                cursor = db.execute(
                    """
                    INSERT INTO purchases (shift_id, name, callsign, reason, note, total_price, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (shift_id, name, callsign, reason, note, total_price, db_timestamp()),
                )
                purchase_id = cursor.lastrowid
                flash("Nákup byl úspěšně přidán.", "success")
            else:
                purchase_id = purchase["id"]
                shift_id = purchase["shift_id"]
                db.execute(
                    "UPDATE purchases SET shift_id = ?, name = ?, callsign = ?, reason = ?, note = ?, total_price = ? WHERE id = ?",
                    (shift_id, name, callsign, reason, note, total_price, purchase_id),
                )
                db.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (purchase_id,))
                flash("Nákup byl úspěšně upraven.", "success")
            for item in parsed_items:
                db.execute(
                    """
                    INSERT INTO purchase_items (purchase_id, item_name, quantity, unit_price, total_price, note)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (purchase_id, item["item_name"], item["quantity"], item["unit_price"], item["total_price"], item["note"]),
                )
            saved_purchase = sync_purchase_message(purchase_id)
            if saved_purchase and saved_purchase["shift_id"]:
                sync_shift_record(saved_purchase["shift_id"])
            db.commit()
            return redirect(url_for("purchases"))
    if items is None:
        items = []
    return render_template("purchase_form.html", purchase=purchase, items=items, catalog=get_catalog(), needs_shift_confirmation=False)


@app.route("/purchases/<int:purchase_id>/delete", methods=["POST"])
def delete_purchase(purchase_id):
    db = get_db()
    purchase = db.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
    if purchase is None:
        flash("Nákup nebyl nalezen.", "danger")
        return redirect(url_for("purchases"))
    db.execute("DELETE FROM purchase_items WHERE purchase_id = ?", (purchase_id,))
    db.execute("DELETE FROM purchases WHERE id = ?", (purchase_id,))
    if purchase["shift_id"]:
        sync_shift_record(purchase["shift_id"])
    db.commit()
    flash("Nákup byl smazán.", "success")
    return redirect(url_for("purchases"))


@app.route("/purchases/export")
def export_purchases():
    rows = get_db().execute(
        """
        SELECT p.id, p.shift_id, p.name, p.callsign, p.reason, p.note AS purchase_note, p.total_price AS purchase_total_price, p.discord_message, p.created_at,
             i.item_name, i.quantity, i.unit_price, i.total_price, i.note AS item_note
        FROM purchases p
        LEFT JOIN purchase_items i ON i.purchase_id = p.id
        ORDER BY p.created_at DESC, p.id DESC, i.id ASC
        """
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID nákupu", "ID směny", "Jméno", "Volací znak", "Důvod", "Poznámka nákupu", "Cena celkem", "Váha celkem", "Discord zpráva", "Vytvořeno", "Položka", "Množství", "Cena/ks", "Váha/ks", "Cena položky", "Váha položky", "Poznámka položky"])
    for row in rows:
        writer.writerow([row["id"], row["shift_id"] or "", row["name"], row["callsign"], row["reason"], row["purchase_note"] or "", row["purchase_total_price"], row["discord_message"] or "", row["created_at"], row["item_name"] or "", row["quantity"] or "", row["unit_price"] or "", row["total_price"] or "", row["item_note"] or ""])
    return csv_response(output.getvalue(), "nakupy.csv")


def csv_response(content, filename):
    return Response(
        "\ufeff" + content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


app.jinja_env.globals.update(
    format_money=format_money,
    format_quantity=format_quantity,
    format_duration=format_duration,
    format_time=format_time,
    format_vehicle_text=format_vehicle_text,
    date_for_input=date_for_input,
    datetime_for_input=datetime_for_input,
)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    host = os.getenv("TRINITY_HOST", "127.0.0.1")
    port = int(os.getenv("TRINITY_PORT", "5000"))
    debug = os.getenv("TRINITY_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug)
