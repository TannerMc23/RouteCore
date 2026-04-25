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
    ("SHP-0001", "CUST-001", "Port of LA, CA",    "Dallas, TX",   "Delivered",  days_ago(12), "",          "FedEx",         "MSKU-1234567", "1Z999AA10123456781", ""),
    ("SHP-0002", "CUST-002", "Chicago, IL",        "Miami, FL",    "In Transit", days_ago(10), "",          "UPS",           "MSKU-2345678", "1Z999AA10123456782", ""),
    ("SHP-0003", "CUST-003", "Seattle, WA",        "Denver, CO",   "Pending",    days_ago(8),  days_ago(2), "DHL",           "MSKU-3456789", "1Z999AA10123456783", ""),
    ("SHP-0004", "CUST-001", "Port of NY, NJ",     "Atlanta, GA",  "In Transit", days_ago(7),  "",          "FedEx",         "MSKU-4567890", "1Z999AA10123456784", ""),
    ("SHP-0005", "CUST-004", "Dallas, TX",         "Phoenix, AZ",  "Delayed",    days_ago(6),  days_ago(1), "USPS",          "MSKU-5678901", "1Z999AA10123456785", ""),
    ("SHP-0006", "CUST-002", "San Francisco, CA",  "Portland, OR", "Delivered",  days_ago(5),  "",          "XPO Logistics", "MSKU-6789012", "1Z999AA10123456786", ""),
]


def seed():
    db = sqlite3.connect(DATABASE)

    db.executescript("""
        PRAGMA journal_mode=WAL;

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
                           CHECK(status IN ('Available', 'On Route', 'Off Duty')),
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
            eta              TEXT DEFAULT '',
            carrier          TEXT DEFAULT '',
            container_number TEXT DEFAULT '',
            tracking_number  TEXT DEFAULT '',
            notes            TEXT DEFAULT '',
            driver_id        TEXT DEFAULT '',
            dispatch_sent    INTEGER DEFAULT 0,
            created_at       TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE INDEX IF NOT EXISTS idx_shipments_customer  ON shipments(customer_id);
        CREATE INDEX IF NOT EXISTS idx_shipments_status    ON shipments(status);
        CREATE INDEX IF NOT EXISTS idx_shipments_carrier   ON shipments(carrier);
        CREATE INDEX IF NOT EXISTS idx_shipments_driver    ON shipments(driver_id);
        CREATE INDEX IF NOT EXISTS idx_drivers_status      ON drivers(status);
    """)

    db.executemany(
        "INSERT OR IGNORE INTO customers (id, name, email, phone, notes) VALUES (?,?,?,?,?)",
        CUSTOMERS,
    )

    db.executemany(
        """INSERT OR IGNORE INTO shipments
           (id, customer_id, origin, destination, status,
            eta, carrier, container_number, tracking_number, notes, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        SHIPMENTS,
    )

    db.commit()
    db.close()
    print(f"Done! Seeded {len(CUSTOMERS)} customers and {len(SHIPMENTS)} shipments.")


if __name__ == "__main__":
    seed()