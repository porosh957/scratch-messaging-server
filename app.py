
import os
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)

# Development/demo CORS only.
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.get("/")
def home():
    return jsonify({
        "name": "Scratch Messaging Server",
        "status": "running",
        "message": "Backend starter API is online.",
        "endpoints": ["/health", "/api/encode", "/api/decode"]
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
        raise ValueError(
            "Each encoded byte must contain exactly 8 binary digits."
        )

    value = int(bits, 2)

    # Decode spaces before checking letter values.
    if value == 52:
        return " "

    lowercase = value % 2 == 1
    index = value // 2

    if index > 25:
        raise ValueError(
            "This byte does not represent a supported character."
        )

    letter = chr(
        (ord("a") if lowercase else ord("A")) + index
    )
    return letter


@app.post("/api/encode")
def encode():
    data = request.get_json(silent=True) or {}
    text = data.get("text")

    if not isinstance(text, str):
        return jsonify({
            "error": 'Send JSON like {"text":"Hello World"}.'
        }), 400

    try:
        encoded = "".join(
            encode_character(char) for char in text
        )
    except ValueError as exc:
        return jsonify({
            "error": str(exc),
            "supported": "English A-Z, a-z, and spaces only"
        }), 400

    return jsonify({
        "text": text,
        "binary": encoded,
        "bytes": [
            encoded[i:i + 8]
            for i in range(0, len(encoded), 8)
        ],
        "character_count": len(text),
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
            "error": (
                "Send a binary string whose length "
                "is a multiple of 8."
            )
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
