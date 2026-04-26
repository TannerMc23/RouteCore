"""
create_admin.py — Create the initial admin account for RouteCore.
Run once after setting up the database:

    python create_admin.py
"""

import sqlite3
import hashlib
import os
from datetime import datetime, timezone

DATABASE = "routecore.db"

ADMIN_NAME     = "Tanner McMillan"
ADMIN_EMAIL    = "tannermcmillan23@gmail.com"
ADMIN_PASSWORD = "TannerMc23!"
ADMIN_ROLE     = "Admin"


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with a salt."""
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def create_admin():
    db = sqlite3.connect(DATABASE)

    # Check if admin already exists
    existing = db.execute(
        "SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,)
    ).fetchone()

    if existing:
        print(f"Admin account already exists for {ADMIN_EMAIL}")
        db.close()
        return

    hashed = hash_password(ADMIN_PASSWORD)
    db.execute(
        "INSERT INTO users (id, name, email, password, role, created_at) VALUES (?,?,?,?,?,?)",
        (
            "USR-001",
            ADMIN_NAME,
            ADMIN_EMAIL,
            hashed,
            ADMIN_ROLE,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        ),
    )
    db.commit()
    db.close()
    print(f"✓ Admin account created for {ADMIN_EMAIL}")
    print(f"  Role: {ADMIN_ROLE}")
    print(f"  Login at: http://127.0.0.1:5000/login or your live URL")


if __name__ == "__main__":
    create_admin()
