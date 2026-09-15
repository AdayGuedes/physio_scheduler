from flask import Flask
from app.extensions import db, login_manager, migrate
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from app.auth import auth
    from app.student import student
    from app.physio import physio
    from app.api import api

    app.register_blueprint(auth)
    app.register_blueprint(student)
    app.register_blueprint(physio)
    app.register_blueprint(api)

    return app