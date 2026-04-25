from flask import Flask, request, jsonify
from flask_cors import CORS
from database import get_db, init_db
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
#  Initialise DB on startup
# ─────────────────────────────────────────
with app.app_context():
    init_db()


# ─────────────────────────────────────────
#  SHIPMENT ENDPOINTS
# ─────────────────────────────────────────

@app.route("/shipments", methods=["GET"])
def get_shipments():
    """Return all shipments, newest first. Optional ?status= filter."""
    db = get_db()
    status_filter = request.args.get("status")
    if status_filter:
        rows = db.execute(
            "SELECT * FROM shipments WHERE status = ? ORDER BY created_at DESC",
            (status_filter,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM shipments ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/shipments/search", methods=["GET"])
def search_shipments():
    """
    Full-text search across shipment fields.
    Usage: GET /shipments/search?q=fedex
    Searches: id, customer_id, origin, destination, status,
              carrier, tracking_number, notes
    """
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
              OR notes            LIKE ?
           ORDER BY created_at DESC""",
        (pattern,) * 8,
    ).fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/shipments/<string:shipment_id>", methods=["GET"])
def get_shipment(shipment_id):
    """Return a single shipment by ID."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    return jsonify(dict(row)), 200


@app.route("/shipments", methods=["POST"])
def create_shipment():
    """Create a new shipment."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    required = ["customer_id", "origin", "destination", "status"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422

    valid_statuses = {"Pending", "In Transit", "Delivered", "Delayed", "Cancelled"}
    if data["status"] not in valid_statuses:
        return jsonify({"error": f"status must be one of: {', '.join(valid_statuses)}"}), 422

    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM shipments").fetchone()[0]
    shipment_id = f"SHP-{(count + 1):04d}"

    db.execute(
        """INSERT INTO shipments
           (id, customer_id, origin, destination, status,
            carrier, tracking_number, eta, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            shipment_id,
            data["customer_id"],
            data["origin"],
            data["destination"],
            data["status"],
            data.get("carrier", ""),
            data.get("tracking_number", ""),
            data.get("eta", ""),
            data.get("notes", ""),
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ),
    )
    db.commit()

    new_row = db.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    return jsonify(dict(new_row)), 201


@app.route("/shipments/<string:shipment_id>", methods=["PUT"])
def update_shipment(shipment_id):
    """Update an existing shipment."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404

    data = request.get_json(silent=True) or {}

    valid_statuses = {"Pending", "In Transit", "Delivered", "Delayed", "Cancelled"}
    if "status" in data and data["status"] not in valid_statuses:
        return jsonify({"error": f"status must be one of: {', '.join(valid_statuses)}"}), 422

    current = dict(row)
    updated = {
        "customer_id":     data.get("customer_id",     current["customer_id"]),
        "origin":          data.get("origin",          current["origin"]),
        "destination":     data.get("destination",     current["destination"]),
        "status":          data.get("status",          current["status"]),
        "carrier":         data.get("carrier",         current.get("carrier", "")),
        "tracking_number": data.get("tracking_number", current.get("tracking_number", "")),
        "eta":             data.get("eta",             current.get("eta", "")),
        "notes":           data.get("notes",           current.get("notes", "")),
    }

    db.execute(
        """UPDATE shipments
           SET customer_id=?, origin=?, destination=?, status=?,
               carrier=?, tracking_number=?, eta=?, notes=?
           WHERE id=?""",
        (
            updated["customer_id"], updated["origin"],
            updated["destination"], updated["status"],
            updated["carrier"],     updated["tracking_number"],
            updated["eta"],         updated["notes"],
            shipment_id,
        ),
    )
    db.commit()

    refreshed = db.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    return jsonify(dict(refreshed)), 200


@app.route("/shipments/<string:shipment_id>", methods=["DELETE"])
def delete_shipment(shipment_id):
    """Delete a shipment by ID."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404

    db.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
    db.commit()
    return jsonify({"message": f"Shipment {shipment_id} deleted"}), 200


# ─────────────────────────────────────────
#  CUSTOMER ENDPOINTS
# ─────────────────────────────────────────

@app.route("/customers", methods=["GET"])
def get_customers():
    """Return all customers."""
    db = get_db()
    rows = db.execute("SELECT * FROM customers ORDER BY name ASC").fetchall()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/customers/<string:customer_id>", methods=["GET"])
def get_customer(customer_id):
    """Return a single customer and their shipments."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Customer not found"}), 404

    shipments = db.execute(
        "SELECT * FROM shipments WHERE customer_id = ? ORDER BY created_at DESC",
        (customer_id,),
    ).fetchall()

    result = dict(row)
    result["shipments"] = [dict(s) for s in shipments]
    return jsonify(result), 200


@app.route("/customers", methods=["POST"])
def create_customer():
    """Create a new customer."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    required = ["name", "email"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422

    db = get_db()
    existing = db.execute(
        "SELECT id FROM customers WHERE email = ?", (data["email"],)
    ).fetchone()
    if existing:
        return jsonify({"error": "A customer with this email already exists"}), 409

    count = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    customer_id = f"CUST-{(count + 1):03d}"

    db.execute(
        """INSERT INTO customers (id, name, email, phone, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (
            customer_id,
            data["name"],
            data["email"],
            data.get("phone", ""),
            data.get("notes", ""),
        ),
    )
    db.commit()

    new_row = db.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    return jsonify(dict(new_row)), 201


@app.route("/customers/<string:customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    """Delete a customer by ID."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
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
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)