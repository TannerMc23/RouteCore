"""
create_admin.py — Create the initial admin account for RouteCore.
Run once after setting up the database:

    python create_admin.py
"""

import os
import hashlib
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")

ADMIN_NAME     = "Tanner McMillan"
ADMIN_EMAIL    = "tannermcmillan23@gmail.com"
ADMIN_PASSWORD = "TannerMc23!"
ADMIN_ROLE     = "Admin"


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def create_admin():
    url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    db  = psycopg2.connect(url)
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id FROM users WHERE email = %s", (ADMIN_EMAIL,))
    if cur.fetchone():
        print(f"Admin account already exists for {ADMIN_EMAIL}")
        db.close()
        return

    cur.execute("SELECT COUNT(*) as c FROM users")
    count   = cur.fetchone()["c"]
    user_id = f"USR-{(count + 1):03d}"
    hashed  = hash_password(ADMIN_PASSWORD)

    cur.execute(
        "INSERT INTO users (id, name, email, password, role, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (user_id, ADMIN_NAME, ADMIN_EMAIL, hashed, ADMIN_ROLE,
         datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    )
    db.commit()
    db.close()
    print(f"✓ Admin account created for {ADMIN_EMAIL}")
    print(f"  Role: {ADMIN_ROLE}")


if __name__ == "__main__":
    create_admin()