import sqlite3
from flask import g, current_app

DATABASE = "routecore.db"


def get_db():
    """Open a database connection scoped to the current request."""
    if "db" not in g:
        g.db = sqlite3.connect(
            DATABASE,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row  # rows behave like dicts
    return g.db


def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't already exist."""
    db = get_db()
    db.executescript("""
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS customers (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL UNIQUE,
            phone       TEXT DEFAULT '',
            notes       TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS shipments (
            id          TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            origin      TEXT NOT NULL,
            destination TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'Pending'
                            CHECK(status IN ('Pending', 'In Transit', 'Delivered')),
            created_at  TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE INDEX IF NOT EXISTS idx_shipments_customer
            ON shipments(customer_id);

        CREATE INDEX IF NOT EXISTS idx_shipments_status
            ON shipments(status);
    """)
    db.commit()

    # Register teardown so the connection closes automatically
    current_app.teardown_appcontext(close_db)
