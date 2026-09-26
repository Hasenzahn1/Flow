from dotenv import load_dotenv
load_dotenv()

import os
import secrets

from flask import Flask
from flask_socketio import SocketIO

from core.db import init_db, migrate
from core.index_db import get_tools
from pages import auth, index
from tools.operation_overview import operation_overview

# Init Flask
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLOW_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
socketio = SocketIO(app)

# Init Database
init_db()
migrate()

# Register Routes
auth.register(app)
index.register(app)
operation_overview.register(app, socketio)


@app.context_processor
def inject_sidebar_tools():
    return {'sidebar_tools': get_tools(only_active=True)}


if __name__ == '__main__':
    tls_cert = os.getenv("FLOW_TLS_CERT", "").strip()
    tls_key = os.getenv("FLOW_TLS_KEY", "").strip()
    if bool(tls_cert) != bool(tls_key):
        raise RuntimeError("FLOW_TLS_CERT und FLOW_TLS_KEY müssen gemeinsam gesetzt werden.")
    run_options = {
        "host": "0.0.0.0",
        "port": 5000,
        "allow_unsafe_werkzeug": True,
    }
    if tls_cert and tls_key:
        run_options["ssl_context"] = (tls_cert, tls_key)
    socketio.run(app, **run_options)
