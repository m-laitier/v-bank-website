from flask import Blueprint
from flask import render_template
from flask_login import current_user


main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    return render_template('main/index.html')


@main_bp.route('/about')
def about():
    return render_template(
        'main/about.html',
        is_logged_in=current_user.is_authenticated
    )
