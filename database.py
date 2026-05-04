import os
import psycopg2
import psycopg2.extras
from flask import g, current_app
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db():
    """Open a PostgreSQL connection scoped to the current request."""
    if "db" not in g:
        # Render provides DATABASE_URL starting with postgres:// but
        # psycopg2 requires postgresql://
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        g.db = psycopg2.connect(url)
        g.db.autocommit = False
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _execute(db, sql, params=None):
    """Execute a statement and return the cursor."""
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params or ())
    return cur


def init_db():
    """Create all tables if they don't exist."""
    db = get_db()

    statements = [
        # Users
        """CREATE TABLE IF NOT EXISTS users (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            email      TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            role       TEXT NOT NULL DEFAULT 'Viewer'
                           CHECK(role IN ('Admin','Dispatcher','Viewer')),
            created_at TEXT NOT NULL
        )""",

        # Customers
        """CREATE TABLE IF NOT EXISTS customers (
            id    TEXT PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )""",

        # Drivers
        """CREATE TABLE IF NOT EXISTS drivers (
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
        )""",

        # Shipments
        """CREATE TABLE IF NOT EXISTS shipments (
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
            created_at       TEXT NOT NULL
        )""",

        # Tasks
        """CREATE TABLE IF NOT EXISTS tasks (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            description     TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'To Do'
                                CHECK(status IN ('To Do','In Progress','Done','Cancelled')),
            priority        TEXT NOT NULL DEFAULT 'Medium'
                                CHECK(priority IN ('Low','Medium','High','Urgent')),
            category        TEXT NOT NULL DEFAULT 'General',
            due_date        TEXT DEFAULT '',
            assigned_user   TEXT DEFAULT '',
            assigned_driver TEXT DEFAULT '',
            shipment_id     TEXT DEFAULT '',
            created_by      TEXT DEFAULT '',
            created_at      TEXT NOT NULL
        )""",

        # Waitlist
        """CREATE TABLE IF NOT EXISTS waitlist (
            id         SERIAL PRIMARY KEY,
            email      TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )""",

        # Indexes
        "CREATE INDEX IF NOT EXISTS idx_shipments_customer  ON shipments(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_status    ON shipments(status)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_carrier   ON shipments(carrier)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_driver    ON shipments(driver_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_type      ON shipments(shipment_type)",
        "CREATE INDEX IF NOT EXISTS idx_drivers_status      ON drivers(status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status        ON tasks(status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_due_date      ON tasks(due_date)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_user ON tasks(assigned_user)",
        "CREATE INDEX IF NOT EXISTS idx_users_email         ON users(email)",
    ]

    for sql in statements:
        _execute(db, sql)

    db.commit()
    current_app.teardown_appcontext(close_db)