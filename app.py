from flask import Flask, request, jsonify
from flask_cors import CORS
from database import get_db, init_db
from datetime import datetime, timezone
from email_service import (
    send_delay_alert,
    send_delivery_confirmation,
    send_dispatch_notification,
)
import os
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

app = Flask(__name__)
CORS(app)

with app.app_context():
    init_db()

ALERT_EMAIL = os.environ.get("ALERT_EMAIL", os.environ.get("FROM_EMAIL", ""))


# ── Helper ─────────────────────────────────────────────────────────────────────

def get_customer_name(db, customer_id: str) -> str:
    row = db.execute("SELECT name FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return row["name"] if row else customer_id


# ─────────────────────────────────────────
#  SHIPMENT ENDPOINTS
# ─────────────────────────────────────────

@app.route("/shipments", methods=["GET"])
def get_shipments():
    db = get_db()
    status_filter = request.args.get("status")
    if status_filter:
        rows = db.execute(
            "SELECT * FROM shipments WHERE status = ? ORDER BY created_at DESC", (status_filter,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM shipments ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/shipments/search", methods=["GET"])
def search_shipments():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([]), 200
    db = get_db()
    pattern = f"%{q}%"
    rows = db.execute(
        """SELECT * FROM shipments
           WHERE id               LIKE ?
              OR customer_id      LIKE ?
              OR origin           LIKE ?
              OR destination      LIKE ?
              OR status           LIKE ?
              OR carrier          LIKE ?
              OR tracking_number  LIKE ?
              OR container_number LIKE ?
              OR notes            LIKE ?
           ORDER BY created_at DESC""",
        (pattern,) * 9,
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/shipments/<string:shipment_id>", methods=["GET"])
def get_shipment(shipment_id):
    db = get_db()
    row = db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    return jsonify(dict(row)), 200


@app.route("/shipments", methods=["POST"])
def create_shipment():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    required = ["customer_id", "origin", "destination", "status"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422

    valid_statuses = {"Pending", "In Transit", "Delivered", "Delayed", "Cancelled"}
    if data["status"] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 422

    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
    shipment_id = f"SHP-{(count + 1):04d}"

    db.execute(
        """INSERT INTO shipments
           (id, customer_id, origin, destination, status,
            carrier, tracking_number, container_number, eta, notes,
            driver_id, dispatch_sent, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
        (
            shipment_id,
            data["customer_id"],
            data["origin"],
            data["destination"],
            data["status"],
            data.get("carrier", ""),
            data.get("tracking_number", ""),
            data.get("container_number", ""),
            data.get("eta", ""),
            data.get("notes", ""),
            data.get("driver_id", ""),
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ),
    )
    db.commit()
    new_row = db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    shipment = dict(new_row)

    # Send alert if created with a triggering status
    if ALERT_EMAIL:
        customer_name = get_customer_name(db, shipment["customer_id"])
        if shipment["status"] == "Delayed":
            send_delay_alert(ALERT_EMAIL, shipment, customer_name)
        elif shipment["status"] == "Delivered":
            send_delivery_confirmation(ALERT_EMAIL, shipment, customer_name)

    return jsonify(shipment), 201


@app.route("/shipments/<string:shipment_id>", methods=["PUT"])
def update_shipment(shipment_id):
    db = get_db()
    row = db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404

    data = request.get_json(silent=True) or {}
    valid_statuses = {"Pending", "In Transit", "Delivered", "Delayed", "Cancelled"}
    if "status" in data and data["status"] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 422

    current       = dict(row)
    previous_status = current["status"]

    updated = {
        "customer_id":      data.get("customer_id",      current["customer_id"]),
        "origin":           data.get("origin",           current["origin"]),
        "destination":      data.get("destination",      current["destination"]),
        "status":           data.get("status",           current["status"]),
        "carrier":          data.get("carrier",          current.get("carrier", "")),
        "tracking_number":  data.get("tracking_number",  current.get("tracking_number", "")),
        "container_number": data.get("container_number", current.get("container_number", "")),
        "eta":              data.get("eta",              current.get("eta", "")),
        "notes":            data.get("notes",            current.get("notes", "")),
        "driver_id":        data.get("driver_id",        current.get("driver_id", "")),
    }

    db.execute(
        """UPDATE shipments
           SET customer_id=?, origin=?, destination=?, status=?,
               carrier=?, tracking_number=?, container_number=?,
               eta=?, notes=?, driver_id=?
           WHERE id=?""",
        (
            updated["customer_id"], updated["origin"], updated["destination"],
            updated["status"], updated["carrier"], updated["tracking_number"],
            updated["container_number"], updated["eta"], updated["notes"],
            updated["driver_id"], shipment_id,
        ),
    )
    db.commit()
    refreshed = dict(db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone())

    # ── Trigger email alerts on status change ──────────────────────
    new_status = updated["status"]
    if ALERT_EMAIL and new_status != previous_status:
        customer_name = get_customer_name(db, refreshed["customer_id"])
        if new_status == "Delayed":
            send_delay_alert(ALERT_EMAIL, refreshed, customer_name)
        elif new_status == "Delivered":
            send_delivery_confirmation(ALERT_EMAIL, refreshed, customer_name)

    return jsonify(refreshed), 200


@app.route("/shipments/<string:shipment_id>/dispatch", methods=["POST"])
def dispatch_shipment(shipment_id):
    db = get_db()
    row = db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404

    shipment = dict(row)
    if not shipment.get("driver_id"):
        return jsonify({"error": "Assign a driver before dispatching"}), 422

    driver_row = db.execute(
        "SELECT * FROM drivers WHERE id = ?", (shipment["driver_id"],)
    ).fetchone()
    if not driver_row:
        return jsonify({"error": "Assigned driver not found"}), 404

    driver = dict(driver_row)

    db.execute(
        "UPDATE shipments SET dispatch_sent=1, status='In Transit' WHERE id=?",
        (shipment_id,)
    )
    db.execute("UPDATE drivers SET status='On Route' WHERE id=?", (driver["id"],))
    db.commit()

    refreshed = dict(db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone())

    # ── Send dispatch email to driver ──────────────────────────────
    email_result = {"success": False, "error": "No driver email on file"}
    if driver.get("email"):
        email_result = send_dispatch_notification(driver["email"], refreshed, driver)
    # Also notify the admin
    if ALERT_EMAIL:
        send_dispatch_notification(ALERT_EMAIL, refreshed, driver)

    dispatch_message = (
        f"RouteCore Dispatch — New Pickup\n\n"
        f"Driver:     {driver['name']}\n"
        f"Phone:      {driver['phone']}\n"
        f"Shipment:   {shipment_id}\n"
        f"Container:  {refreshed.get('container_number') or 'N/A'}\n"
        f"Pickup:     {refreshed['origin']}\n"
        f"Deliver to: {refreshed['destination']}\n"
        f"ETA:        {refreshed.get('eta') or 'TBD'}\n"
        f"Carrier:    {refreshed.get('carrier') or 'N/A'}\n"
        f"Notes:      {refreshed.get('notes') or 'None'}"
    )

    return jsonify({
        "shipment":         refreshed,
        "driver":           driver,
        "dispatch_message": dispatch_message,
        "email_sent":       email_result.get("success", False),
        "message":          f"Dispatched. Driver {driver['name']} notified for {shipment_id}."
    }), 200


@app.route("/shipments/<string:shipment_id>", methods=["DELETE"])
def delete_shipment(shipment_id):
    db = get_db()
    row = db.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    db.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
    db.commit()
    return jsonify({"message": f"Shipment {shipment_id} deleted"}), 200


# ─────────────────────────────────────────
#  DRIVER ENDPOINTS
# ─────────────────────────────────────────

@app.route("/drivers", methods=["GET"])
def get_drivers():
    db = get_db()
    rows = db.execute("SELECT * FROM drivers ORDER BY name ASC").fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/drivers/<string:driver_id>", methods=["GET"])
def get_driver(driver_id):
    db = get_db()
    row = db.execute("SELECT * FROM drivers WHERE id = ?", (driver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Driver not found"}), 404
    driver = dict(row)
    shipments = db.execute(
        "SELECT * FROM shipments WHERE driver_id = ? ORDER BY created_at DESC", (driver_id,)
    ).fetchall()
    driver["shipments"] = [dict(s) for s in shipments]
    return jsonify(driver), 200


@app.route("/drivers", methods=["POST"])
def create_driver():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    required = ["name", "phone"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM drivers").fetchone()[0]
    driver_id = f"DRV-{(count + 1):03d}"
    db.execute(
        """INSERT INTO drivers (id, name, phone, email, license, carrier, status, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'Available', ?, ?)""",
        (
            driver_id, data["name"], data["phone"],
            data.get("email", ""), data.get("license", ""),
            data.get("carrier", ""), data.get("notes", ""),
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ),
    )
    db.commit()
    new_row = db.execute("SELECT * FROM drivers WHERE id = ?", (driver_id,)).fetchone()
    return jsonify(dict(new_row)), 201


@app.route("/drivers/<string:driver_id>", methods=["PUT"])
def update_driver(driver_id):
    db = get_db()
    row = db.execute("SELECT * FROM drivers WHERE id = ?", (driver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Driver not found"}), 404
    data = request.get_json(silent=True) or {}
    valid_statuses = {"Available", "On Route", "Off Duty"}
    if "status" in data and data["status"] not in valid_statuses:
        return jsonify({"error": "Invalid driver status"}), 422
    current = dict(row)
    db.execute(
        """UPDATE drivers SET name=?, phone=?, email=?, license=?, carrier=?, status=?, notes=?
           WHERE id=?""",
        (
            data.get("name",    current["name"]),
            data.get("phone",   current["phone"]),
            data.get("email",   current.get("email", "")),
            data.get("license", current.get("license", "")),
            data.get("carrier", current.get("carrier", "")),
            data.get("status",  current["status"]),
            data.get("notes",   current.get("notes", "")),
            driver_id,
        ),
    )
    db.commit()
    refreshed = db.execute("SELECT * FROM drivers WHERE id = ?", (driver_id,)).fetchone()
    return jsonify(dict(refreshed)), 200


@app.route("/drivers/<string:driver_id>", methods=["DELETE"])
def delete_driver(driver_id):
    db = get_db()
    row = db.execute("SELECT * FROM drivers WHERE id = ?", (driver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Driver not found"}), 404
    db.execute("DELETE FROM drivers WHERE id = ?", (driver_id,))
    db.commit()
    return jsonify({"message": f"Driver {driver_id} deleted"}), 200


# ─────────────────────────────────────────
#  CUSTOMER ENDPOINTS
# ─────────────────────────────────────────

@app.route("/customers", methods=["GET"])
def get_customers():
    db = get_db()
    rows = db.execute("SELECT * FROM customers ORDER BY name ASC").fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/customers/<string:customer_id>", methods=["GET"])
def get_customer(customer_id):
    db = get_db()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not row:
        return jsonify({"error": "Customer not found"}), 404
    shipments = db.execute(
        "SELECT * FROM shipments WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)
    ).fetchall()
    result = dict(row)
    result["shipments"] = [dict(s) for s in shipments]
    return jsonify(result), 200


@app.route("/customers", methods=["POST"])
def create_customer():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    required = ["name", "email"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422
    db = get_db()
    existing = db.execute("SELECT id FROM customers WHERE email = ?", (data["email"],)).fetchone()
    if existing:
        return jsonify({"error": "A customer with this email already exists"}), 409
    count = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    customer_id = f"CUST-{(count + 1):03d}"
    db.execute(
        "INSERT INTO customers (id, name, email, phone, notes) VALUES (?, ?, ?, ?, ?)",
        (customer_id, data["name"], data["email"], data.get("phone", ""), data.get("notes", "")),
    )
    db.commit()
    new_row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return jsonify(dict(new_row)), 201


@app.route("/customers/<string:customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    db = get_db()
    row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not row:
        return jsonify({"error": "Customer not found"}), 404
    db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    db.commit()
    return jsonify({"message": f"Customer {customer_id} deleted"}), 200


# ─────────────────────────────────────────
#  HEALTH CHECK
# ─────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "email_configured": bool(ALERT_EMAIL),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)