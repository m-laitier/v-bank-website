from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import url_for
from flask_login import current_user
from flask_login import login_required
from flask_login import login_user
from flask_login import logout_user

from app.auth.forms import LoginForm
from app.auth.forms import RegisterForm
from app.auth.models import User
from app.auth.storage import create_user
from app.auth.storage import get_user_by_phone
from app.auth.validators import normalize_phone


auth_bp = Blueprint(
    'auth',
    __name__,
    url_prefix='/auth'
)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('cabinet.cabinet'))

    form = RegisterForm()

    if form.validate_on_submit():
        phone = normalize_phone(form.phone.data.strip())

        if get_user_by_phone(phone):
            form.phone.errors.append('Пользователь с таким номером уже существует')
        else:
            create_user(
                form.full_name.data.strip(),
                phone,
                form.password.data
            )
            user_data = get_user_by_phone(phone)
            user = User(user_data)
            login_user(user)
            return redirect(url_for('auth.success'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('cabinet.cabinet'))

    form = LoginForm()

    if form.validate_on_submit():
        phone = normalize_phone(form.phone.data.strip())
        user_data = get_user_by_phone(phone)

        if not user_data:
            form.phone.errors.append('Пользователь не найден')
        elif user_data['password'] != form.password.data:
            form.password.errors.append('Неверный пароль')
        else:
            user = User(user_data)
            login_user(user)
            return redirect(url_for('cabinet.cabinet'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/success')
@login_required
def success():
    return render_template('auth/success.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))
