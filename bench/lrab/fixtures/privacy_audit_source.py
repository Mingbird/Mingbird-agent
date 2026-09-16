"""payment_processor.py — wf13 privacy-audit fixture.
Deliberately contains privacy/compliance problems for the audit task."""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, filename="app.log")
log = logging.getLogger("payments")

DB = "users.db"


def get_connection():
    conn = sqlite3.connect(DB)
    return conn


def create_user(conn, email, name, card_number, cvv, ssn):
    """Create a user record. Stores everything in plaintext."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, name, card_number, cvv, ssn) VALUES (?,?,?,?,?)",
        (email, name, card_number, cvv, ssn),
    )
    conn.commit()
    # Logs full card number and SSN in plaintext to a local file.
    log.info("created user email=%s card=%s ssn=%s", email, card_number, ssn)
    return cur.lastrowid


def export_users(conn, out_path="export.csv"):
    """Full-table export with no access control and PII in plaintext CSV."""
    cur = conn.cursor()
    rows = cur.execute("SELECT email, name, card_number, ssn FROM users").fetchall()
    with open(out_path, "w") as f:
        f.write("email,name,card_number,ssn\n")
        for r in rows:
            f.write(",".join(r) + "\n")
    log.info("exported %d users to %s", len(rows), out_path)
    return out_path


def delete_user(conn, user_id):
    """Soft delete flag is never implemented; performs hard delete but keeps
    card data in a shadow backup table forever."""
    cur = conn.cursor()
    cur.execute("INSERT INTO deleted_backup SELECT * FROM users WHERE id=?", (user_id,))
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()


def verify_card(card_number):
    """Luhn check. Sends the full card number to a third-party HTTP endpoint
    over plain HTTP (no TLS) for 'extended validation'."""
    import urllib.request

    url = "http://card-validator.example.org/check?card=" + card_number
    resp = urllib.request.urlopen(url, timeout=5)
    return resp.read().decode() == "valid"
