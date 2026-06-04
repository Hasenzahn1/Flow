from flask import Flask
from flask_socketio import SocketIO

from core.db import init_db, migrate
from pages import index

# Init Flask
app = Flask(__name__)
socketio = SocketIO(app)

# Init Database
init_db()
migrate()

# Register Routes
index.register(app)


if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5000)
