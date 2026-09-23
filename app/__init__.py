from flask import Flask

from app.api import api
from app.auth import auth
from app.extensions import db, login_manager, migrate
from app.physio import physio
from app.student import student
from app import models
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(auth)
    app.register_blueprint(student)
    app.register_blueprint(physio)
    app.register_blueprint(api)

    return app
