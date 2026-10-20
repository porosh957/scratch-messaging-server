import os
import hmac
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

# Development/demo CORS only. Restrict origins before production use.
CORS(app, resources={r"/api/*": {"origins": "*"}})


def database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_db_connection():
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return psycopg.connect(url, row_factory=dict_row)


def ensure_user_table():
    """Create the registry table if it does not exist yet."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                username_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


@app.get("/")
def home():
    return jsonify({
        "name": "Scratch Messaging Server",
        "status": "running",
        "message": "Backend API is online.",
        "endpoints": [
            "/health",
            "/api/encode",
            "/api/decode",
            "/api/users",
            "/api/users/register",
            "/api/users/<id>",
            "/api/users/lookup?username=<username>",
            "DELETE /api/users/<id> (requires X-Admin-Token)"
        ]
    })


@app.get("/health")
def health():
    return jsonify({"ok": True})


# Encoding:
# A-Z = even values 0-50
# a-z = odd values 1-51
# space = value 52

def encode_character(char):
    if char == " ":
        return format(52, "08b")

    if "A" <= char <= "Z":
        index = ord(char) - ord("A")
        return format(index * 2, "08b")

    if "a" <= char <= "z":
        index = ord(char) - ord("a")
        return format(index * 2 + 1, "08b")

    raise ValueError(f"Unsupported character: {char!r}")


def decode_byte(bits):
    if len(bits) != 8 or any(bit not in "01" for bit in bits):
        raise ValueError("Each encoded byte must contain exactly 8 binary digits.")

    value = int(bits, 2)
    if value == 52:
        return " "

    lowercase = value % 2 == 1
    index = value // 2
    if index > 25:
        raise ValueError("This byte does not represent a supported character.")

    return chr((ord("a") if lowercase else ord("A")) + index)


@app.post("/api/encode")
def encode():
    data = request.get_json(silent=True) or {}
    message = data.get("text")

    if not isinstance(message, str):
        return jsonify({"error": 'Send JSON like {"text":"Hello World"}.'}), 400

    try:
        encoded = "".join(encode_character(char) for char in message)
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
            "supported": "English A-Z, a-z, and spaces only"
        }), 400

    return jsonify({
        "text": message,
        "binary": encoded,
        "bytes": [encoded[i:i + 8] for i in range(0, len(encoded), 8)],
        "character_count": len(message),
        "bit_count": len(encoded)
    })


@app.post("/api/decode")
def decode():
    data = request.get_json(silent=True) or {}
    binary = data.get("binary")

    if (
        not isinstance(binary, str)
        or len(binary) % 8 != 0
        or any(bit not in "01" for bit in binary)
    ):
        return jsonify({
            "error": "Send a binary string whose length is a multiple of 8."
        }), 400

    try:
        decoded = "".join(
            decode_byte(binary[i:i + 8])
            for i in range(0, len(binary), 8)
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "binary": binary,
        "text": decoded,
        "character_count": len(decoded)
    })


def normalize_username(value):
    if not isinstance(value, str):
        return None
    username = value.strip()
    if not username or len(username) > 100:
        return None
    return username


def database_error_response(exc):
    app.logger.exception("User registry database error: %s", exc)
    return jsonify({
        "error": "User registry database is unavailable. Check DATABASE_URL and database status."
    }), 503


@app.post("/api/users/register")
def register_user():
    data = request.get_json(silent=True) or {}
    username = normalize_username(data.get("username"))

    if username is None:
        return jsonify({
            "error": "Provide a username containing 1 to 100 characters."
        }), 400

    username_key = username.casefold()

    try:
        ensure_user_table()
        with get_db_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO users (username, username_key)
                VALUES (%s, %s)
                ON CONFLICT (username_key) DO NOTHING
                RETURNING id, username
                """,
                (username, username_key)
            ).fetchone()

            created = row is not None
            if row is None:
                row = conn.execute(
                    "SELECT id, username FROM users WHERE username_key = %s",
                    (username_key,)
                ).fetchone()

        return jsonify({
            "id": row["id"],
            "username": row["username"],
            "created": created
        }), 201 if created else 200
    except (psycopg.Error, RuntimeError) as exc:
        return database_error_response(exc)


@app.get("/api/users")
def list_users():
    try:
        ensure_user_table()
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT id, username FROM users ORDER BY id ASC"
            ).fetchall()
        # This endpoint deliberately returns an array, not an object wrapper.
        return jsonify([{"id": row["id"], "username": row["username"]} for row in rows])
    except (psycopg.Error, RuntimeError) as exc:
        return database_error_response(exc)


@app.get("/api/users/<int:user_id>")
def get_user_by_id(user_id):
    try:
        ensure_user_table()
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, username FROM users WHERE id = %s",
                (user_id,)
            ).fetchone()

        if row is None:
            return jsonify({"error": "User ID not found."}), 404
        return jsonify({"id": row["id"], "username": row["username"]})
    except (psycopg.Error, RuntimeError) as exc:
        return database_error_response(exc)


@app.delete("/api/users/<int:user_id>")
def delete_user(user_id):
    """
    Permanently delete a registry user.
    Configure DELETE_TOKEN in the server environment and send it in
    the X-Admin-Token header. This route is intentionally protected.
    """
    configured_token = os.environ.get("DELETE_TOKEN", "")
    supplied_token = request.headers.get("X-Admin-Token", "")

    if not configured_token:
        return jsonify({
            "error": "Deletion is disabled until DELETE_TOKEN is configured on the server."
        }), 503

    if not supplied_token or not hmac.compare_digest(supplied_token, configured_token):
        return jsonify({"error": "Unauthorized."}), 401

    try:
        ensure_user_table()
        with get_db_connection() as conn:
            row = conn.execute(
                "DELETE FROM users WHERE id = %s RETURNING id, username",
                (user_id,)
            ).fetchone()

        if row is None:
            return jsonify({"error": "User ID not found."}), 404

        return jsonify({
            "deleted": True,
            "id": row["id"],
            "username": row["username"]
        })
    except (psycopg.Error, RuntimeError) as exc:
        return database_error_response(exc)


@app.get("/api/users/lookup")
def lookup_user_by_username():
    username = normalize_username(request.args.get("username"))
    if username is None:
        return jsonify({
            "error": "Provide a username query parameter."
        }), 400

    try:
        ensure_user_table()
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT id, username FROM users WHERE username_key = %s",
                (username.casefold(),)
            ).fetchone()

        if row is None:
            return jsonify({"error": "Username not found."}), 404
        return jsonify({"id": row["id"], "username": row["username"]})
    except (psycopg.Error, RuntimeError) as exc:
        return database_error_response(exc)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
