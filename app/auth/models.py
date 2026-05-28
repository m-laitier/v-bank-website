from flask_login import UserMixin


class User(UserMixin):
    """Обёртка над словарём пользователя для Flask-Login."""

    def __init__(self, data: dict):
        self._data = data

    # Flask-Login требует строковый id
    def get_id(self):
        return self._data['phone']

    # Удобные свойства для шаблонов
    @property
    def phone(self):
        return self._data['phone']

    @property
    def full_name(self):
        return self._data.get('full_name', '')

    @property
    def first_name(self):
        parts = self.full_name.split()
        return parts[0] if parts else ''

    @property
    def data(self):
        return self._data
