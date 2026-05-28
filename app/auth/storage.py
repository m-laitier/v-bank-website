import json
import os
import uuid


DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'data',
    'users.json'
)


DEFAULT_ACCOUNTS = {
    'rub': 150000.0,
    'rub2': 150000.0,
    'savings': 50000.0
}


def _default_accounts():
    return {
        'rub': DEFAULT_ACCOUNTS['rub'],
        'rub2': DEFAULT_ACCOUNTS['rub2'],
        'savings': DEFAULT_ACCOUNTS['savings']
    }


def _ensure_user_schema(user):
    changed = False

    if 'id' not in user:
        user['id'] = str(uuid.uuid4())
        changed = True

    if 'is_admin' not in user:
        user['is_admin'] = False
        changed = True

    if 'accounts' not in user:
        user['accounts'] = _default_accounts()
        changed = True

    if 'transactions' not in user:
        user['transactions'] = []
        changed = True

    return changed


def load_users():
    if not os.path.exists(DATA_FILE):
        return []

    if os.path.getsize(DATA_FILE) == 0:
        return []

    with open(DATA_FILE, 'r', encoding='utf-8') as file:
        try:
            users = json.load(file)
            changed = False

            if not isinstance(users, list):
                return []

            for user in users:
                if _ensure_user_schema(user):
                    changed = True

            if changed:
                save_users(users)

            return users

        except json.JSONDecodeError:
            return []



def save_users(users):
    with open(DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(
            users,
            file,
            ensure_ascii=False,
            indent=4
        )



def get_user_by_phone(phone):
    users = load_users()

    for user in users:
        if user['phone'] == phone:
            return user

    return None


def get_user_by_id(user_id):
    users = load_users()

    for user in users:
        if user.get('id') == user_id:
            return user

    return None


def list_users():
    return load_users()



def create_user(full_name, phone, password, is_admin=False):
    users = load_users()

    users.append({
        'id': str(uuid.uuid4()),
        'full_name': full_name,
        'phone': phone,
        'password': password,
        'is_admin': bool(is_admin),
        'accounts': _default_accounts(),
        'transactions': []
    })

    save_users(users)



def update_user(updated_user, old_phone=None):
    """Обновляет данные пользователя. Если передан old_phone, поиск идёт по нему,
    иначе – по номеру внутри updated_user."""
    users = load_users()
    phone_to_find = old_phone if old_phone else updated_user['phone']

    for index, user in enumerate(users):
        if user['phone'] == phone_to_find:
            _ensure_user_schema(updated_user)
            users[index] = updated_user
            break

    save_users(users)


def delete_user_by_id(user_id):
    users = load_users()
    initial_count = len(users)
    users = [user for user in users if user.get('id') != user_id]

    if len(users) == initial_count:
        return False

    save_users(users)
    return True