"""
seed.py — Populate RouteCore with sample customers and shipments.
Run once before starting the server:

    python seed.py
"""

import sqlite3
from datetime import datetime, timedelta, timezone

DATABASE = "routecore.db"

CUSTOMERS = [
    ("CUST-001", "Apex Logistics",    "ops@apexlogistics.com",       "+1 (212) 555-0101", "Priority account"),
    ("CUST-002", "BlueLine Freight",  "contact@bluelinefreight.com", "+1 (312) 555-0202", "Net-30 terms"),
    ("CUST-003", "Summit Cargo",      "info@summitcargo.com",        "+1 (206) 555-0303", ""),
    ("CUST-004", "Meridian Express",  "hello@meridianexpress.com",   "+1 (469) 555-0404", "New account"),
]

def days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")

SHIPMENTS = [
    ("SHP-0001", "CUST-001", "New York, US",      "Los Angeles, US", "Delivered",  days_ago(12)),
    ("SHP-0002", "CUST-002", "Chicago, US",        "Miami, US",       "In Transit", days_ago(10)),
    ("SHP-0003", "CUST-003", "Seattle, US",        "Denver, US",      "Pending",    days_ago(8)),
    ("SHP-0004", "CUST-001", "Boston, US",         "Atlanta, US",     "In Transit", days_ago(7)),
    ("SHP-0005", "CUST-004", "Dallas, US",         "Phoenix, US",     "Pending",    days_ago(6)),
    ("SHP-0006", "CUST-002", "San Francisco, US",  "Portland, US",    "Delivered",  days_ago(5)),
]


def seed():
    db = sqlite3.connect(DATABASE)

    # Create tables if they don't exist yet
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

    # Insert sample data
    db.executemany(
        "INSERT OR IGNORE INTO customers (id, name, email, phone, notes) VALUES (?,?,?,?,?)",
        CUSTOMERS,
    )
    db.executemany(
        """INSERT OR IGNORE INTO shipments
           (id, customer_id, origin, destination, status, created_at)
           VALUES (?,?,?,?,?,?)""",
        SHIPMENTS,
    )

    db.commit()
    db.close()
    print(f"Done! Seeded {len(CUSTOMERS)} customers and {len(SHIPMENTS)} shipments.")


if __name__ == "__main__":
    seed()