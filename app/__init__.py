import os

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from app.api.routes import api_bp
from app.auth.routes import auth_bp
from app.cabinet.routes import cabinet_bp
from app.main.routes import main_bp

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    app.config.from_object('app.config.Config')

    os.makedirs(app.instance_path, exist_ok=True)

    # Инициализация расширений
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите в систему'
    login_manager.login_message_category = 'error'

    csrf.init_app(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cabinet_bp)
    app.register_blueprint(api_bp)
    csrf.exempt(api_bp)

    # Загрузчик пользователя для Flask-Login
    from app.auth.models import User
    from app.auth.storage import get_user_by_phone

    @login_manager.user_loader
    def load_user(phone):
        data = get_user_by_phone(phone)
        if data:
            return User(data)
        return None

    # Контекстный процессор: имя пользователя в шаблонах
    from flask_login import current_user

    @app.context_processor
    def inject_user_name():
        if current_user.is_authenticated:
            return {'user_name': current_user.first_name}
        return {'user_name': None}

    return app
