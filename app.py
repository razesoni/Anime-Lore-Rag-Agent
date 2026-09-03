from flask import Flask, jsonify

from config import settings


app = Flask(__name__)


@app.get("/")
def home():
    return jsonify(
        {
            "name": "Akashic-RAG",
            "description": (
                "Domain-Specific Hybrid Lore Engine"
            ),
            "status": "online",
        }
    )


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "healthy",
        }
    )


if __name__ == "__main__":
    app.run(
        host="[IP_ADDRESS]",
        port=settings.port,
        debug=settings.flask_debug,
    )