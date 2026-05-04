from flask import Flask, request, jsonify
from flask_cors import CORS
from database import get_db, init_db, _execute
from datetime import datetime, timezone
from email_service import (
    send_delay_alert,
    send_delivery_confirmation,
    send_dispatch_notification,
)
import os
import hashlib
import secrets
import functools
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, origins=[
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://tannermc23.github.io",
    "*"
])

with app.app_context():
    init_db()

ALERT_EMAIL  = os.environ.get("ALERT_EMAIL", os.environ.get("FROM_EMAIL", ""))
active_tokens = {}


# ─────────────────────────────────────────
#  AUTH HELPERS
# ─────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return key.hex() == key_hex
    except Exception:
        return False


def get_token_from_request():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_auth(roles=None):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            token = get_token_from_request()
            if not token or token not in active_tokens:
                return jsonify({"error": "Unauthorized — please log in"}), 401
            user_data = active_tokens[token]
            if roles and user_data["role"] not in roles:
                return jsonify({"error": f"Forbidden — requires role: {', '.join(roles)}"}), 403
            request.current_user = user_data
            return f(*args, **kwargs)
        return wrapped
    return decorator


def get_customer_name(db, customer_id: str) -> str:
    cur = _execute(db, "SELECT name FROM customers WHERE id = %s", (customer_id,))
    row = cur.fetchone()
    return row["name"] if row else customer_id


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ─────────────────────────────────────────
#  AUTH ENDPOINTS
# ─────────────────────────────────────────

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT * FROM users WHERE email = %s", (email,))
    row = cur.fetchone()
    if not row or not verify_password(password, row["password"]):
        return jsonify({"error": "Invalid email or password"}), 401
    user  = dict(row)
    token = secrets.token_hex(32)
    active_tokens[token] = {
        "user_id": user["id"], "email": user["email"],
        "name": user["name"], "role": user["role"],
    }
    return jsonify({"token": token, "id": user["id"], "name": user["name"],
                    "email": user["email"], "role": user["role"]}), 200


@app.route("/auth/logout", methods=["POST"])
def logout():
    token = get_token_from_request()
    if token and token in active_tokens:
        del active_tokens[token]
    return jsonify({"message": "Logged out"}), 200


@app.route("/auth/me", methods=["GET"])
def me():
    token = get_token_from_request()
    if not token or token not in active_tokens:
        return jsonify({"error": "Not authenticated"}), 401
    user = active_tokens[token]
    return jsonify({"id": user["user_id"], "name": user["name"],
                    "email": user["email"], "role": user["role"]}), 200


@app.route("/auth/register", methods=["POST"])
@require_auth(["Admin"])
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    required = ["name", "email", "password", "role"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422
    valid_roles = {"Admin", "Dispatcher", "Viewer"}
    if data["role"] not in valid_roles:
        return jsonify({"error": "Invalid role"}), 422
    if len(data["password"]) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT id FROM users WHERE email = %s", (data["email"].lower(),))
    if cur.fetchone():
        return jsonify({"error": "A user with this email already exists"}), 409
    cur     = _execute(db, "SELECT COUNT(*) as c FROM users")
    count   = cur.fetchone()["c"]
    user_id = f"USR-{(count + 1):03d}"
    hashed  = hash_password(data["password"])
    _execute(db,
        "INSERT INTO users (id, name, email, password, role, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (user_id, data["name"], data["email"].lower(), hashed, data["role"], now()))
    db.commit()
    cur = _execute(db, "SELECT id, name, email, role, created_at FROM users WHERE id = %s", (user_id,))
    return jsonify(dict(cur.fetchone())), 201


@app.route("/auth/users", methods=["GET"])
@require_auth(["Admin"])
def get_users():
    db  = get_db()
    cur = _execute(db, "SELECT id, name, email, role, created_at FROM users ORDER BY created_at ASC")
    return jsonify([dict(r) for r in cur.fetchall()]), 200


@app.route("/auth/users/<string:user_id>", methods=["PUT"])
@require_auth(["Admin"])
def update_user(user_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json(silent=True) or {}
    valid_roles = {"Admin", "Dispatcher", "Viewer"}
    if "role" in data and data["role"] not in valid_roles:
        return jsonify({"error": "Invalid role"}), 422
    current = dict(row)
    _execute(db, "UPDATE users SET name=%s, role=%s WHERE id=%s",
             (data.get("name", current["name"]), data.get("role", current["role"]), user_id))
    db.commit()
    cur = _execute(db, "SELECT id, name, email, role, created_at FROM users WHERE id = %s", (user_id,))
    return jsonify(dict(cur.fetchone())), 200


@app.route("/auth/users/<string:user_id>", methods=["DELETE"])
@require_auth(["Admin"])
def delete_user(user_id):
    if user_id == request.current_user["user_id"]:
        return jsonify({"error": "You cannot delete your own account"}), 400
    db  = get_db()
    cur = _execute(db, "SELECT * FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        return jsonify({"error": "User not found"}), 404
    _execute(db, "DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()
    return jsonify({"message": f"User {user_id} deleted"}), 200


# ─────────────────────────────────────────
#  TASK ENDPOINTS
# ─────────────────────────────────────────

VALID_TASK_STATUSES   = {"To Do", "In Progress", "Done", "Cancelled"}
VALID_TASK_PRIORITIES = {"Low", "Medium", "High", "Urgent"}


@app.route("/tasks", methods=["GET"])
@require_auth()
def get_tasks():
    db     = get_db()
    status = request.args.get("status")
    user   = request.args.get("assigned_user")
    sql    = "SELECT * FROM tasks WHERE 1=1"
    params = []
    if status:
        sql += " AND status = %s"; params.append(status)
    if user:
        sql += " AND assigned_user = %s"; params.append(user)
    sql += """ ORDER BY CASE priority
                WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3 ELSE 4 END, due_date ASC"""
    cur = _execute(db, sql, params)
    return jsonify([dict(r) for r in cur.fetchall()]), 200


@app.route("/tasks/calendar", methods=["GET"])
@require_auth()
def get_calendar():
    db     = get_db()
    year   = request.args.get("year",  datetime.now(timezone.utc).year)
    month  = request.args.get("month", datetime.now(timezone.utc).month)
    prefix = f"{year}-{str(month).zfill(2)}"
    cur    = _execute(db, "SELECT * FROM tasks WHERE due_date LIKE %s ORDER BY due_date ASC", (prefix + "%",))
    tasks  = [dict(r) for r in cur.fetchall()]
    cur    = _execute(db, "SELECT id, customer_id, origin, destination, status, shipment_type, eta FROM shipments WHERE eta LIKE %s", (prefix + "%",))
    ships  = [dict(r) for r in cur.fetchall()]
    return jsonify({"tasks": tasks, "shipments": ships, "year": int(year), "month": int(month)}), 200


@app.route("/tasks/<string:task_id>", methods=["GET"])
@require_auth()
def get_task(task_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(dict(row)), 200


@app.route("/tasks", methods=["POST"])
@require_auth(["Admin", "Dispatcher"])
def create_task():
    data = request.get_json(silent=True)
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 422
    if data.get("status") and data["status"] not in VALID_TASK_STATUSES:
        return jsonify({"error": "Invalid status"}), 422
    if data.get("priority") and data["priority"] not in VALID_TASK_PRIORITIES:
        return jsonify({"error": "Invalid priority"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT COUNT(*) as c FROM tasks")
    tid = f"TSK-{(cur.fetchone()['c'] + 1):04d}"
    _execute(db,
        """INSERT INTO tasks
           (id,title,description,status,priority,category,
            due_date,assigned_user,assigned_driver,shipment_id,created_by,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (tid, data["title"], data.get("description",""),
         data.get("status","To Do"), data.get("priority","Medium"),
         data.get("category","General"), data.get("due_date",""),
         data.get("assigned_user",""), data.get("assigned_driver",""),
         data.get("shipment_id",""), request.current_user["user_id"], now()))
    db.commit()
    cur = _execute(db, "SELECT * FROM tasks WHERE id = %s", (tid,))
    return jsonify(dict(cur.fetchone())), 201


@app.route("/tasks/<string:task_id>", methods=["PUT"])
@require_auth(["Admin", "Dispatcher"])
def update_task(task_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Task not found"}), 404
    data = request.get_json(silent=True) or {}
    if data.get("status") and data["status"] not in VALID_TASK_STATUSES:
        return jsonify({"error": "Invalid status"}), 422
    if data.get("priority") and data["priority"] not in VALID_TASK_PRIORITIES:
        return jsonify({"error": "Invalid priority"}), 422
    current = dict(row)
    _execute(db,
        """UPDATE tasks SET title=%s,description=%s,status=%s,priority=%s,
           category=%s,due_date=%s,assigned_user=%s,assigned_driver=%s,shipment_id=%s
           WHERE id=%s""",
        (data.get("title",current["title"]), data.get("description",current.get("description","")),
         data.get("status",current["status"]), data.get("priority",current["priority"]),
         data.get("category",current.get("category","General")),
         data.get("due_date",current.get("due_date","")),
         data.get("assigned_user",current.get("assigned_user","")),
         data.get("assigned_driver",current.get("assigned_driver","")),
         data.get("shipment_id",current.get("shipment_id","")), task_id))
    db.commit()
    cur = _execute(db, "SELECT * FROM tasks WHERE id = %s", (task_id,))
    return jsonify(dict(cur.fetchone())), 200


@app.route("/tasks/<string:task_id>", methods=["DELETE"])
@require_auth(["Admin", "Dispatcher"])
def delete_task(task_id):
    db  = get_db()
    cur = _execute(db, "SELECT id FROM tasks WHERE id = %s", (task_id,))
    if not cur.fetchone():
        return jsonify({"error": "Task not found"}), 404
    _execute(db, "DELETE FROM tasks WHERE id = %s", (task_id,))
    db.commit()
    return jsonify({"message": f"Task {task_id} deleted"}), 200


# ─────────────────────────────────────────
#  SHIPMENT ENDPOINTS
# ─────────────────────────────────────────

@app.route("/shipments", methods=["GET"])
@require_auth()
def get_shipments():
    db     = get_db()
    status = request.args.get("status")
    stype  = request.args.get("type")
    sql    = "SELECT * FROM shipments WHERE 1=1"
    params = []
    if status:
        sql += " AND status = %s"; params.append(status)
    if stype:
        sql += " AND shipment_type = %s"; params.append(stype)
    sql += " ORDER BY created_at DESC"
    cur = _execute(db, sql, params)
    return jsonify([dict(r) for r in cur.fetchall()]), 200


@app.route("/shipments/search", methods=["GET"])
@require_auth()
def search_shipments():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([]), 200
    db      = get_db()
    pattern = f"%{q}%"
    cur     = _execute(db,
        """SELECT * FROM shipments
           WHERE id               ILIKE %s OR customer_id      ILIKE %s
              OR origin           ILIKE %s OR destination      ILIKE %s
              OR status           ILIKE %s OR shipment_type    ILIKE %s
              OR carrier          ILIKE %s OR tracking_number  ILIKE %s
              OR container_number ILIKE %s OR notes            ILIKE %s
           ORDER BY created_at DESC""",
        (pattern,)*10)
    return jsonify([dict(r) for r in cur.fetchall()]), 200


@app.route("/shipments/<string:shipment_id>", methods=["GET"])
@require_auth()
def get_shipment(shipment_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    return jsonify(dict(row)), 200


@app.route("/shipments", methods=["POST"])
@require_auth(["Admin", "Dispatcher"])
def create_shipment():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    required = ["customer_id", "origin", "destination", "status"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422
    valid_statuses = {"Pending","In Transit","Delivered","Delayed","Cancelled"}
    if data["status"] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT COUNT(*) as c FROM shipments")
    sid = f"SHP-{(cur.fetchone()['c'] + 1):04d}"
    _execute(db,
        """INSERT INTO shipments
           (id,customer_id,origin,destination,status,shipment_type,
            carrier,tracking_number,container_number,eta,notes,
            driver_id,dispatch_sent,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s)""",
        (sid, data["customer_id"], data["origin"], data["destination"],
         data["status"], data.get("shipment_type","Other"),
         data.get("carrier",""), data.get("tracking_number",""),
         data.get("container_number",""), data.get("eta",""),
         data.get("notes",""), data.get("driver_id",""), now()))
    db.commit()
    cur      = _execute(db, "SELECT * FROM shipments WHERE id = %s", (sid,))
    shipment = dict(cur.fetchone())
    if ALERT_EMAIL:
        customer_name = get_customer_name(db, shipment["customer_id"])
        if shipment["status"] == "Delayed":
            send_delay_alert(ALERT_EMAIL, shipment, customer_name)
        elif shipment["status"] == "Delivered":
            send_delivery_confirmation(ALERT_EMAIL, shipment, customer_name)
    return jsonify(shipment), 201


@app.route("/shipments/<string:shipment_id>", methods=["PUT"])
@require_auth(["Admin", "Dispatcher"])
def update_shipment(shipment_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    data = request.get_json(silent=True) or {}
    valid_statuses = {"Pending","In Transit","Delivered","Delayed","Cancelled"}
    if "status" in data and data["status"] not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 422
    current         = dict(row)
    previous_status = current["status"]
    updated = {
        "customer_id":      data.get("customer_id",      current["customer_id"]),
        "origin":           data.get("origin",           current["origin"]),
        "destination":      data.get("destination",      current["destination"]),
        "status":           data.get("status",           current["status"]),
        "shipment_type":    data.get("shipment_type",    current.get("shipment_type","Other")),
        "carrier":          data.get("carrier",          current.get("carrier","")),
        "tracking_number":  data.get("tracking_number",  current.get("tracking_number","")),
        "container_number": data.get("container_number", current.get("container_number","")),
        "eta":              data.get("eta",              current.get("eta","")),
        "notes":            data.get("notes",            current.get("notes","")),
        "driver_id":        data.get("driver_id",        current.get("driver_id","")),
    }
    _execute(db,
        """UPDATE shipments SET customer_id=%s,origin=%s,destination=%s,status=%s,
           shipment_type=%s,carrier=%s,tracking_number=%s,container_number=%s,
           eta=%s,notes=%s,driver_id=%s WHERE id=%s""",
        (updated["customer_id"], updated["origin"], updated["destination"],
         updated["status"], updated["shipment_type"], updated["carrier"],
         updated["tracking_number"], updated["container_number"],
         updated["eta"], updated["notes"], updated["driver_id"], shipment_id))
    db.commit()
    cur       = _execute(db, "SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    refreshed = dict(cur.fetchone())
    if ALERT_EMAIL and updated["status"] != previous_status:
        customer_name = get_customer_name(db, refreshed["customer_id"])
        if updated["status"] == "Delayed":
            send_delay_alert(ALERT_EMAIL, refreshed, customer_name)
        elif updated["status"] == "Delivered":
            send_delivery_confirmation(ALERT_EMAIL, refreshed, customer_name)
    return jsonify(refreshed), 200


@app.route("/shipments/<string:shipment_id>/dispatch", methods=["POST"])
@require_auth(["Admin", "Dispatcher"])
def dispatch_shipment(shipment_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    shipment = dict(row)
    if not shipment.get("driver_id"):
        return jsonify({"error": "Assign a driver before dispatching"}), 422
    cur = _execute(db, "SELECT * FROM drivers WHERE id = %s", (shipment["driver_id"],))
    driver_row = cur.fetchone()
    if not driver_row:
        return jsonify({"error": "Assigned driver not found"}), 404
    driver = dict(driver_row)
    _execute(db, "UPDATE shipments SET dispatch_sent=1, status='In Transit' WHERE id=%s", (shipment_id,))
    _execute(db, "UPDATE drivers SET status='On Route' WHERE id=%s", (driver["id"],))
    db.commit()
    cur       = _execute(db, "SELECT * FROM shipments WHERE id = %s", (shipment_id,))
    refreshed = dict(cur.fetchone())
    if driver.get("email"):
        send_dispatch_notification(driver["email"], refreshed, driver)
    if ALERT_EMAIL:
        send_dispatch_notification(ALERT_EMAIL, refreshed, driver)
    return jsonify({"shipment": refreshed, "driver": driver,
                    "message": f"Dispatched. Driver {driver['name']} notified for {shipment_id}."}), 200


@app.route("/shipments/<string:shipment_id>", methods=["DELETE"])
@require_auth(["Admin"])
def delete_shipment(shipment_id):
    db  = get_db()
    cur = _execute(db, "SELECT id FROM shipments WHERE id = %s", (shipment_id,))
    if not cur.fetchone():
        return jsonify({"error": "Shipment not found"}), 404
    _execute(db, "DELETE FROM shipments WHERE id = %s", (shipment_id,))
    db.commit()
    return jsonify({"message": f"Shipment {shipment_id} deleted"}), 200


# ─────────────────────────────────────────
#  DRIVER ENDPOINTS
# ─────────────────────────────────────────

@app.route("/drivers", methods=["GET"])
@require_auth()
def get_drivers():
    db  = get_db()
    cur = _execute(db, "SELECT * FROM drivers ORDER BY name ASC")
    return jsonify([dict(r) for r in cur.fetchall()]), 200


@app.route("/drivers", methods=["POST"])
@require_auth(["Admin", "Dispatcher"])
def create_driver():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    required = ["name", "phone"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT COUNT(*) as c FROM drivers")
    did = f"DRV-{(cur.fetchone()['c'] + 1):03d}"
    _execute(db,
        """INSERT INTO drivers (id,name,phone,email,license,carrier,status,notes,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,'Available',%s,%s)""",
        (did, data["name"], data["phone"], data.get("email",""),
         data.get("license",""), data.get("carrier",""),
         data.get("notes",""), now()))
    db.commit()
    cur = _execute(db, "SELECT * FROM drivers WHERE id = %s", (did,))
    return jsonify(dict(cur.fetchone())), 201


@app.route("/drivers/<string:driver_id>", methods=["PUT"])
@require_auth(["Admin", "Dispatcher"])
def update_driver(driver_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM drivers WHERE id = %s", (driver_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Driver not found"}), 404
    data    = request.get_json(silent=True) or {}
    current = dict(row)
    valid_statuses = {"Available","On Route","Off Duty"}
    if "status" in data and data["status"] not in valid_statuses:
        return jsonify({"error": "Invalid driver status"}), 422
    _execute(db,
        "UPDATE drivers SET name=%s,phone=%s,email=%s,license=%s,carrier=%s,status=%s,notes=%s WHERE id=%s",
        (data.get("name",current["name"]), data.get("phone",current["phone"]),
         data.get("email",current.get("email","")), data.get("license",current.get("license","")),
         data.get("carrier",current.get("carrier","")), data.get("status",current["status"]),
         data.get("notes",current.get("notes","")), driver_id))
    db.commit()
    cur = _execute(db, "SELECT * FROM drivers WHERE id = %s", (driver_id,))
    return jsonify(dict(cur.fetchone())), 200


@app.route("/drivers/<string:driver_id>", methods=["DELETE"])
@require_auth(["Admin"])
def delete_driver(driver_id):
    db  = get_db()
    cur = _execute(db, "SELECT id FROM drivers WHERE id = %s", (driver_id,))
    if not cur.fetchone():
        return jsonify({"error": "Driver not found"}), 404
    _execute(db, "DELETE FROM drivers WHERE id = %s", (driver_id,))
    db.commit()
    return jsonify({"message": f"Driver {driver_id} deleted"}), 200


# ─────────────────────────────────────────
#  CUSTOMER ENDPOINTS
# ─────────────────────────────────────────

@app.route("/customers", methods=["GET"])
@require_auth()
def get_customers():
    db  = get_db()
    cur = _execute(db, "SELECT * FROM customers ORDER BY name ASC")
    return jsonify([dict(r) for r in cur.fetchall()]), 200


@app.route("/customers", methods=["POST"])
@require_auth(["Admin", "Dispatcher"])
def create_customer():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    required = ["name", "email"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT id FROM customers WHERE email = %s", (data["email"],))
    if cur.fetchone():
        return jsonify({"error": "A customer with this email already exists"}), 409
    cur = _execute(db, "SELECT COUNT(*) as c FROM customers")
    cid = f"CUST-{(cur.fetchone()['c'] + 1):03d}"
    _execute(db,
        "INSERT INTO customers (id,name,email,phone,notes) VALUES (%s,%s,%s,%s,%s)",
        (cid, data["name"], data["email"], data.get("phone",""), data.get("notes","")))
    db.commit()
    cur = _execute(db, "SELECT * FROM customers WHERE id = %s", (cid,))
    return jsonify(dict(cur.fetchone())), 201


@app.route("/customers/<string:customer_id>", methods=["DELETE"])
@require_auth(["Admin"])
def delete_customer(customer_id):
    db  = get_db()
    cur = _execute(db, "SELECT id FROM customers WHERE id = %s", (customer_id,))
    if not cur.fetchone():
        return jsonify({"error": "Customer not found"}), 404
    _execute(db, "DELETE FROM customers WHERE id = %s", (customer_id,))
    db.commit()
    return jsonify({"message": f"Customer {customer_id} deleted"}), 200


# ─────────────────────────────────────────
#  WAITLIST
# ─────────────────────────────────────────

@app.route("/waitlist", methods=["POST"])
def join_waitlist():
    data = request.get_json(silent=True)
    if not data or not data.get("email"):
        return jsonify({"error": "Email is required"}), 422
    email = data["email"].strip().lower()
    if "@" not in email:
        return jsonify({"error": "Invalid email address"}), 422
    db  = get_db()
    cur = _execute(db, "SELECT id FROM waitlist WHERE email = %s", (email,))
    if cur.fetchone():
        return jsonify({"message": "Already on the waitlist"}), 409
    _execute(db, "INSERT INTO waitlist (email, created_at) VALUES (%s, %s)",
             (email, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()
    cur   = _execute(db, "SELECT COUNT(*) as c FROM waitlist")
    count = cur.fetchone()["c"]
    if ALERT_EMAIL:
        try:
            import resend as resend_client
            resend_client.api_key = os.environ.get("RESEND_API_KEY", "")
            resend_client.Emails.send({
                "from":    os.environ.get("FROM_EMAIL", "onboarding@resend.dev"),
                "to":      [ALERT_EMAIL],
                "subject": f"🎉 New Waitlist Signup — {email}",
                "html":    f"<p>New signup: <strong>{email}</strong><br>Total signups: {count}</p>",
            })
        except Exception:
            pass
    return jsonify({"message": "Successfully joined the waitlist"}), 201


@app.route("/waitlist", methods=["GET"])
@require_auth(["Admin"])
def get_waitlist():
    db  = get_db()
    cur = _execute(db, "SELECT * FROM waitlist ORDER BY created_at DESC")
    return jsonify([dict(r) for r in cur.fetchall()]), 200


# ─────────────────────────────────────────
#  PUBLIC CUSTOMER PORTAL
# ─────────────────────────────────────────

@app.route("/portal/shipment/<string:shipment_id>", methods=["GET"])
def portal_get_shipment(shipment_id):
    db  = get_db()
    cur = _execute(db, "SELECT * FROM shipments WHERE id = %s", (shipment_id.upper(),))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Shipment not found"}), 404
    s = dict(row)
    return jsonify({
        "id":               s["id"],
        "origin":           s["origin"],
        "destination":      s["destination"],
        "status":           s["status"],
        "shipment_type":    s.get("shipment_type","Other"),
        "carrier":          s.get("carrier",""),
        "tracking_number":  s.get("tracking_number",""),
        "container_number": s.get("container_number",""),
        "eta":              s.get("eta",""),
        "notes":            s.get("notes",""),
        "created_at":       s.get("created_at",""),
    }), 200


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