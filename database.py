import sqlite3
from flask import g, current_app

DATABASE = "routecore.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()

    # ── Step 1: Migrate existing shipments table ──────────────
    try:
        existing_cols = {row[1] for row in db.execute("PRAGMA table_info(shipments)").fetchall()}
        shipment_migrations = {
            "carrier":          "ALTER TABLE shipments ADD COLUMN carrier TEXT DEFAULT ''",
            "tracking_number":  "ALTER TABLE shipments ADD COLUMN tracking_number TEXT DEFAULT ''",
            "eta":              "ALTER TABLE shipments ADD COLUMN eta TEXT DEFAULT ''",
            "notes":            "ALTER TABLE shipments ADD COLUMN notes TEXT DEFAULT ''",
            "driver_id":        "ALTER TABLE shipments ADD COLUMN driver_id TEXT DEFAULT ''",
            "container_number": "ALTER TABLE shipments ADD COLUMN container_number TEXT DEFAULT ''",
            "dispatch_sent":    "ALTER TABLE shipments ADD COLUMN dispatch_sent INTEGER DEFAULT 0",
            "shipment_type":    "ALTER TABLE shipments ADD COLUMN shipment_type TEXT DEFAULT 'Other'",
        }
        for col, sql in shipment_migrations.items():
            if col not in existing_cols:
                db.execute(sql)
        db.commit()
    except Exception:
        pass

    # ── Step 2: Create all tables ─────────────────────────────
    db.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS waitlist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            email      TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            role       TEXT NOT NULL DEFAULT 'Viewer'
                           CHECK(role IN ('Admin','Dispatcher','Viewer')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            id    TEXT PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS drivers (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            phone      TEXT NOT NULL,
            email      TEXT DEFAULT '',
            license    TEXT DEFAULT '',
            carrier    TEXT DEFAULT '',
            status     TEXT NOT NULL DEFAULT 'Available'
                           CHECK(status IN ('Available','On Route','Off Duty')),
            notes      TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shipments (
            id               TEXT PRIMARY KEY,
            customer_id      TEXT NOT NULL,
            origin           TEXT NOT NULL,
            destination      TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'Pending'
                                 CHECK(status IN ('Pending','In Transit','Delivered','Delayed','Cancelled')),
            shipment_type    TEXT NOT NULL DEFAULT 'Other',
            carrier          TEXT DEFAULT '',
            tracking_number  TEXT DEFAULT '',
            container_number TEXT DEFAULT '',
            eta              TEXT DEFAULT '',
            notes            TEXT DEFAULT '',
            driver_id        TEXT DEFAULT '',
            dispatch_sent    INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id            TEXT PRIMARY KEY,
            title         TEXT NOT NULL,
            description   TEXT DEFAULT '',
            status        TEXT NOT NULL DEFAULT 'To Do'
                              CHECK(status IN ('To Do','In Progress','Done','Cancelled')),
            priority      TEXT NOT NULL DEFAULT 'Medium'
                              CHECK(priority IN ('Low','Medium','High','Urgent')),
            category      TEXT NOT NULL DEFAULT 'General',
            due_date      TEXT DEFAULT '',
            assigned_user TEXT DEFAULT '',
            assigned_driver TEXT DEFAULT '',
            shipment_id   TEXT DEFAULT '',
            created_by    TEXT DEFAULT '',
            created_at    TEXT NOT NULL,
            FOREIGN KEY (shipment_id) REFERENCES shipments(id)
        );

        CREATE INDEX IF NOT EXISTS idx_shipments_customer  ON shipments(customer_id);
        CREATE INDEX IF NOT EXISTS idx_shipments_status    ON shipments(status);
        CREATE INDEX IF NOT EXISTS idx_shipments_carrier   ON shipments(carrier);
        CREATE INDEX IF NOT EXISTS idx_shipments_driver    ON shipments(driver_id);
        CREATE INDEX IF NOT EXISTS idx_shipments_type      ON shipments(shipment_type);
        CREATE INDEX IF NOT EXISTS idx_drivers_status      ON drivers(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_status        ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_due_date      ON tasks(due_date);
        CREATE INDEX IF NOT EXISTS idx_tasks_assigned_user ON tasks(assigned_user);
        CREATE INDEX IF NOT EXISTS idx_users_email         ON users(email);
    """)
    db.commit()

    # ── Step 3: Migrate drivers if needed ─────────────────────
    try:
        existing_driver_cols = {row[1] for row in db.execute("PRAGMA table_info(drivers)").fetchall()}
        driver_migrations = {
            "license": "ALTER TABLE drivers ADD COLUMN license TEXT DEFAULT ''",
            "carrier": "ALTER TABLE drivers ADD COLUMN carrier TEXT DEFAULT ''",
        }
        for col, sql in driver_migrations.items():
            if col not in existing_driver_cols:
                db.execute(sql)
        db.commit()
    except Exception:
        pass

    current_app.teardown_appcontext(close_db)