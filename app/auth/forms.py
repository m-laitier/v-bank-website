import re

from flask_wtf import FlaskForm
from wtforms import PasswordField
from wtforms import StringField
from wtforms import SubmitField
from wtforms.validators import DataRequired
from wtforms.validators import EqualTo
from wtforms.validators import Length
from wtforms.validators import Regexp
from wtforms.validators import ValidationError

from app.auth.validators import validate_full_name
from app.auth.validators import validate_password


PHONE_REGEX = r'^(\+7|8)\d{10}$'


class RegisterForm(FlaskForm):
    full_name = StringField(
        'Фамилия, имя',
        validators=[
            DataRequired(message='Обязательное поле'),
            Length(max=100, message='Не более 100 символов'),
        ]
    )
    phone = StringField(
        'Номер телефона',
        validators=[
            DataRequired(message='Обязательное поле'),
            Regexp(
                PHONE_REGEX,
                message='Формат: +79991234567 или 89991234567'
            ),
        ]
    )
    password = PasswordField(
        'Придумайте пароль',
        validators=[
            DataRequired(message='Обязательное поле'),
            Length(min=5, max=25, message='От 5 до 25 символов'),
        ]
    )
    confirm_password = PasswordField(
        'Подтвердите пароль',
        validators=[
            DataRequired(message='Обязательное поле'),
            EqualTo('password', message='Пароли не совпадают'),
        ]
    )
    submit = SubmitField('Оформить карту')

    def validate_full_name(self, field):
        if not validate_full_name(field.data):
            raise ValidationError(
                'Только кириллица, пробел и дефис'
            )

    def validate_password(self, field):
        if not validate_password(field.data):
            raise ValidationError(
                'Только латинские буквы, цифры и спецсимволы'
            )


class LoginForm(FlaskForm):
    phone = StringField(
        'Номер телефона',
        validators=[
            DataRequired(message='Обязательное поле'),
            Regexp(
                PHONE_REGEX,
                message='Формат: +79991234567 или 89991234567'
            ),
        ]
    )
    password = PasswordField(
        'Пароль',
        validators=[
            DataRequired(message='Обязательное поле'),
        ]
    )
    submit = SubmitField('Войти')
