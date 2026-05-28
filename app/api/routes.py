import datetime
import secrets

from flask import Blueprint
from flask import jsonify
from flask import request

from app.auth.storage import create_user
from app.auth.storage import delete_user_by_id
from app.auth.storage import get_user_by_phone
from app.auth.storage import list_users
from app.auth.storage import update_user
from app.auth.validators import normalize_phone
from app.auth.validators import validate_full_name
from app.auth.validators import validate_password
from app.auth.validators import validate_phone


api_bp = Blueprint('api', __name__, url_prefix='/api')

USER_TOKENS = {}
ADMIN_TOKENS = {}


def _json_error(message, code=400):
    return jsonify({'success': False, 'message': message}), code


def _extract_bearer_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    return auth_header[7:].strip()


def _issue_token(storage, phone):
    token = secrets.token_urlsafe(24)
    storage[token] = phone
    return token


def _sanitize_user(user):
    return {
        'id': user.get('id'),
        'full_name': user.get('full_name', ''),
        'phone': user.get('phone', ''),
        'is_admin': bool(user.get('is_admin', False))
    }


def _parse_autopayment_date(date_str):
    for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _get_user_by_token():
    token = _extract_bearer_token()
    if not token or token not in USER_TOKENS:
        return None
    return get_user_by_phone(USER_TOKENS[token])


def _get_admin_by_token():
    token = _extract_bearer_token()
    if not token or token not in ADMIN_TOKENS:
        return None
    admin = get_user_by_phone(ADMIN_TOKENS[token])
    if not admin or not admin.get('is_admin', False):
        return None
    return admin


@api_bp.route('/auth/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True) or {}

    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    password = data.get('password') or ''

    if not validate_full_name(full_name):
        return _json_error('Некорректное ФИО')

    if not validate_phone(phone):
        return _json_error('Некорректный номер телефона')

    phone = normalize_phone(phone)

    if not validate_password(password):
        return _json_error('Некорректный пароль')

    if get_user_by_phone(phone):
        return _json_error('Пользователь с таким номером уже существует')

    create_user(full_name, phone, password)
    token = _issue_token(USER_TOKENS, phone)
    return jsonify({'success': True, 'token': token, 'phone': phone})


@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    phone = normalize_phone((data.get('phone') or '').strip())
    password = data.get('password') or ''

    user = get_user_by_phone(phone)
    if not user:
        return _json_error('Пользователь не найден', 404)

    if user.get('password') != password:
        return _json_error('Неверный пароль', 401)

    token = _issue_token(USER_TOKENS, phone)
    return jsonify({'success': True, 'token': token, 'user': _sanitize_user(user)})


@api_bp.route('/profile', methods=['GET'])
def api_profile():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    payload = _sanitize_user(user)
    payload['accounts'] = user.get('accounts', {})
    return jsonify({'success': True, 'user': payload})


@api_bp.route('/cabinet', methods=['GET'])
def api_cabinet():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    transactions = user.get('transactions', [])
    monthly_spent = sum(
        t.get('amount', 0)
        for t in transactions
        if t.get('type', 'debit') == 'debit'
    )
    return jsonify({
        'success': True,
        'user': {
            'full_name': user.get('full_name', ''),
            'phone': user.get('phone', ''),
            'accounts': user.get('accounts', {})
        },
        'monthly_spent': monthly_spent
    })


@api_bp.route('/transactions', methods=['GET'])
def api_transactions():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    return jsonify({'success': True, 'transactions': user.get('transactions', [])})


@api_bp.route('/payments', methods=['GET'])
def api_payments():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    transactions = user.get('transactions', [])
    now = datetime.datetime.now()
    current_prefix = f'{now.year}-{now.month:02d}'
    monthly_spent = sum(
        float(t.get('amount', 0))
        for t in transactions
        if t.get('type') == 'debit'
        and t.get('date', '').startswith(current_prefix)
    )
    return jsonify({
        'success': True,
        'transactions': transactions,
        'monthly_spent': monthly_spent
    })


@api_bp.route('/transfer', methods=['POST'])
def api_transfer():
    sender = _get_user_by_token()
    if not sender:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    account = data.get('account')
    recipient_phone = normalize_phone((data.get('recipient_phone') or '').strip())
    amount_raw = data.get('amount')

    if account not in ['rub', 'rub2']:
        return _json_error('Выберите корректный счет')

    if not validate_phone(recipient_phone):
        return _json_error('Некорректный номер получателя')

    if recipient_phone == sender.get('phone'):
        return _json_error('Нельзя переводить самому себе')

    recipient = get_user_by_phone(recipient_phone)
    if not recipient:
        return _json_error('Получатель не является клиентом банка', 404)

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return _json_error('Некорректная сумма')

    if amount <= 0:
        return _json_error('Некорректная сумма')

    if amount > sender.get('accounts', {}).get(account, 0):
        return _json_error('Недостаточно средств')

    now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    sender['accounts'][account] -= amount
    sender.setdefault('transactions', [])
    sender['transactions'].append({
        'date': now_str,
        'amount': amount,
        'type': 'debit',
        'recipient_phone': recipient_phone
    })
    update_user(sender)

    recipient.setdefault('accounts', {})
    recipient['accounts'][account] = recipient['accounts'].get(account, 0) + amount
    recipient.setdefault('transactions', [])
    recipient['transactions'].append({
        'date': now_str,
        'amount': amount,
        'type': 'credit',
        'from_phone': sender.get('phone')
    })
    update_user(recipient)

    return jsonify({'success': True, 'message': 'Перевод выполнен успешно'})


@api_bp.route('/profile/change-phone', methods=['POST'])
def api_change_phone():
    user = _get_user_by_token()
    token = _extract_bearer_token()
    if not user or not token:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    new_phone = (data.get('phone') or '').strip()

    if not new_phone:
        return _json_error('Номер не указан')

    if not validate_phone(new_phone):
        return _json_error('Некорректный номер')

    new_phone = normalize_phone(new_phone)

    if new_phone == user.get('phone'):
        return _json_error('Это ваш текущий номер')

    if get_user_by_phone(new_phone):
        return _json_error('Номер уже используется')

    old_phone = user['phone']
    user['phone'] = new_phone
    update_user(user, old_phone=old_phone)
    USER_TOKENS[token] = new_phone

    return jsonify({'success': True, 'message': 'Телефон обновлён'})


@api_bp.route('/profile/change-password', methods=['POST'])
def api_change_password():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''
    repeat_password = data.get('repeat_password') or ''

    if user.get('password') != current_password:
        return _json_error('Неверный текущий пароль')

    if not validate_password(new_password):
        return _json_error('Некорректный пароль')

    if current_password == new_password:
        return _json_error('Новый пароль совпадает с текущим')

    if new_password != repeat_password:
        return _json_error('Пароли не совпадают')

    user['password'] = new_password
    update_user(user)
    return jsonify({'success': True, 'message': 'Пароль изменён'})


@api_bp.route('/autopayments/list', methods=['GET'])
def api_autopayments_list():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)
    return jsonify({'success': True, 'payments': user.get('autopayments', [])})


@api_bp.route('/autopayments/add', methods=['POST'])
def api_autopayments_add():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()
    amount_raw = data.get('amount')
    date_str = (data.get('date') or '').strip()

    if not validate_phone(phone):
        return _json_error('Некорректный номер получателя')

    phone = normalize_phone(phone)
    if phone == user.get('phone'):
        return _json_error('Нельзя указывать свой номер телефона')

    if not get_user_by_phone(phone):
        return _json_error('Получатель не найден в базе банка')

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _json_error('Некорректная сумма')

    if not date_str:
        return _json_error('Укажите дату автоплатежа')

    parsed = _parse_autopayment_date(date_str)
    if not parsed:
        return _json_error('Некорректная дата')
    if parsed < datetime.date.today():
        return _json_error('Дата не может быть в прошлом')
    display_date = parsed.strftime('%d.%m.%Y')
    date_iso = parsed.strftime('%Y-%m-%d')

    user.setdefault('autopayments', [])
    user['autopayments'].append({
        'phone': phone,
        'amount': amount,
        'date': display_date,
        'date_iso': date_iso
    })
    update_user(user)
    return jsonify({'success': True, 'message': 'Автоплатёж добавлен'})


@api_bp.route('/autopayments/edit', methods=['PATCH'])
def api_autopayments_edit():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    try:
        idx = int(data.get('index'))
    except (TypeError, ValueError):
        return _json_error('Неверный индекс')

    autopayments = user.get('autopayments', [])
    if idx < 0 or idx >= len(autopayments):
        return _json_error('Автоплатёж не найден')

    field = data.get('field')
    value = str(data.get('value') or '').strip()

    if field == 'amount':
        try:
            val = float(value)
            if val <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return _json_error('Некорректная сумма')
        autopayments[idx]['amount'] = val
    elif field == 'date':
        parsed = _parse_autopayment_date(value)
        if not parsed:
            return _json_error('Некорректная дата')
        if parsed < datetime.date.today():
            return _json_error('Дата не может быть в прошлом')
        autopayments[idx]['date'] = parsed.strftime('%d.%m.%Y')
        autopayments[idx]['date_iso'] = parsed.strftime('%Y-%m-%d')
    else:
        return _json_error('Недопустимое поле')

    user['autopayments'] = autopayments
    update_user(user)
    return jsonify({'success': True, 'message': 'Сохранено'})


@api_bp.route('/autopayments/delete', methods=['DELETE'])
def api_autopayments_delete():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    try:
        idx = int(data.get('index'))
    except (TypeError, ValueError):
        return _json_error('Неверный индекс')

    autopayments = user.get('autopayments', [])
    if idx < 0 or idx >= len(autopayments):
        return _json_error('Автоплатёж не найден')

    autopayments.pop(idx)
    user['autopayments'] = autopayments
    update_user(user)
    return jsonify({'success': True, 'message': 'Удалено'})


CASHBACK_CATEGORIES = {
    'all': '1% все покупки',
    'restaurants': '3% рестораны',
    'education': '2% образование',
    'partners': '5% у партнёров',
    'travel': '7% путешествия'
}


@api_bp.route('/cashback', methods=['GET'])
def api_cashback_get():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)
    return jsonify({
        'success': True,
        'selected': user.get('cashback_categories', []),
        'categories': CASHBACK_CATEGORIES
    })


@api_bp.route('/cashback', methods=['POST'])
def api_cashback_set():
    user = _get_user_by_token()
    if not user:
        return _json_error('Требуется авторизация', 401)

    data = request.get_json(silent=True) or {}
    chosen = data.get('categories') or []
    if not isinstance(chosen, list):
        return _json_error('Некорректный формат категорий')

    valid_keys = set(CASHBACK_CATEGORIES.keys())
    chosen = [item for item in chosen if item in valid_keys]

    if len(chosen) != 3:
        return _json_error('Необходимо выбрать ровно 3 категории')

    user['cashback_categories'] = chosen
    update_user(user)
    return jsonify({'success': True, 'message': 'Категории кэшбэка сохранены', 'selected': chosen})


@api_bp.route('/admin/register', methods=['POST'])
def admin_register():
    data = request.get_json(silent=True) or {}

    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    password = data.get('password') or ''

    if not validate_full_name(full_name):
        return _json_error('Некорректное ФИО')

    if not validate_phone(phone):
        return _json_error('Некорректный номер телефона')

    phone = normalize_phone(phone)

    if not validate_password(password):
        return _json_error('Некорректный пароль')

    existing = get_user_by_phone(phone)
    if existing and not existing.get('is_admin', False):
        return _json_error('Номер уже используется обычным пользователем')
    if existing and existing.get('is_admin', False):
        return _json_error('Администратор с таким номером уже существует')

    create_user(full_name, phone, password, is_admin=True)
    token = _issue_token(ADMIN_TOKENS, phone)
    return jsonify({'success': True, 'token': token, 'phone': phone})


@api_bp.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    phone = normalize_phone((data.get('phone') or '').strip())
    password = data.get('password') or ''

    admin = get_user_by_phone(phone)
    if not admin or not admin.get('is_admin', False):
        return _json_error('Администратор не найден', 404)

    if admin.get('password') != password:
        return _json_error('Неверный пароль', 401)

    token = _issue_token(ADMIN_TOKENS, phone)
    return jsonify({'success': True, 'token': token, 'admin': _sanitize_user(admin)})


@api_bp.route('/admin/users', methods=['GET'])
def admin_list_users():
    admin = _get_admin_by_token()
    if not admin:
        return _json_error('Требуется авторизация администратора', 401)

    users = [_sanitize_user(user) for user in list_users()]
    return jsonify({'success': True, 'users': users})


@api_bp.route('/admin/users', methods=['POST'])
def admin_create_user():
    admin = _get_admin_by_token()
    if not admin:
        return _json_error('Требуется авторизация администратора', 401)

    data = request.get_json(silent=True) or {}
    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    password = data.get('password') or ''

    if not validate_full_name(full_name):
        return _json_error('Некорректное ФИО')

    if not validate_phone(phone):
        return _json_error('Некорректный номер телефона')

    phone = normalize_phone(phone)

    if not validate_password(password):
        return _json_error('Некорректный пароль')

    if get_user_by_phone(phone):
        return _json_error('Пользователь с таким номером уже существует')

    create_user(full_name, phone, password)
    user = get_user_by_phone(phone)
    return jsonify({'success': True, 'user': _sanitize_user(user)})


@api_bp.route('/admin/users/<user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    admin = _get_admin_by_token()
    if not admin:
        return _json_error('Требуется авторизация администратора', 401)

    users = list_users()
    target = None
    for user in users:
        if user.get('id') == user_id:
            target = user
            break

    if not target:
        return _json_error('Пользователь не найден', 404)

    if target.get('is_admin', False):
        return _json_error('Удаление администратора запрещено', 403)

    if not delete_user_by_id(user_id):
        return _json_error('Пользователь не найден', 404)

    return jsonify({'success': True, 'message': 'Пользователь удален'})
