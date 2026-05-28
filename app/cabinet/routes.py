import datetime

from flask import Blueprint
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import url_for
from flask_login import current_user
from flask_login import login_required

from app.auth.storage import get_user_by_phone
from app.auth.storage import update_user
from app.auth.validators import normalize_phone
from app.auth.validators import validate_password
from app.auth.validators import validate_phone


cabinet_bp = Blueprint(
    'cabinet',
    __name__,
    url_prefix='/cabinet'
)


def _get_current_user_data():
    """Возвращает актуальный словарь текущего пользователя из хранилища."""
    return get_user_by_phone(current_user.phone)


@cabinet_bp.route('/')
@login_required
def cabinet():
    user = _get_current_user_data()

    if 'transactions' not in user:
        user['transactions'] = []

    monthly_spent = sum(
        t.get('amount', 0)
        for t in user['transactions']
        if t.get('type', 'debit') == 'debit'
    )

    return render_template(
        'cabinet/cabinet.html',
        user=user,
        monthly_spent=monthly_spent
    )


@cabinet_bp.route('/profile')
@login_required
def profile():
    user = _get_current_user_data()
    return render_template('cabinet/profile.html', user=user)


@cabinet_bp.route('/change-phone', methods=['POST'])
@login_required
def change_phone():
    new_phone = (request.form.get('phone') or '').strip()

    if not new_phone:
        return jsonify({'success': False, 'message': 'Номер не указан'})

    new_phone = normalize_phone(new_phone)

    if not validate_phone(new_phone):
        return jsonify({'success': False, 'message': 'Некорректный номер'})

    if new_phone == current_user.phone:
        return jsonify({'success': False, 'message': 'Это ваш текущий номер'})

    if get_user_by_phone(new_phone):
        return jsonify({'success': False, 'message': 'Номер уже используется'})

    user = _get_current_user_data()
    old_phone = user['phone']
    user['phone'] = new_phone
    update_user(user, old_phone=old_phone)

    # Переавторизуем пользователя с новым phone (новым id)
    from flask_login import login_user
    from app.auth.models import User
    login_user(User(user))

    return jsonify({'success': True, 'message': 'Телефон обновлён'})


@cabinet_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    repeat_password = request.form.get('repeat_password', '')

    user = _get_current_user_data()

    if user['password'] != current_password:
        return jsonify({'success': False, 'message': 'Неверный текущий пароль'})

    if not validate_password(new_password):
        return jsonify({'success': False, 'message': 'Некорректный пароль'})

    if current_password == new_password:
        return jsonify({'success': False, 'message': 'Новый пароль совпадает с текущим'})

    if new_password != repeat_password:
        return jsonify({'success': False, 'message': 'Пароли не совпадают'})

    user['password'] = new_password
    update_user(user)

    return jsonify({'success': True, 'message': 'Пароль изменён'})


@cabinet_bp.route('/transactions')
@login_required
def transactions():
    user = _get_current_user_data()

    if 'transactions' not in user:
        user['transactions'] = []

    return render_template(
        'cabinet/transactions.html',
        transactions=user['transactions']
    )


@cabinet_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    user = _get_current_user_data()

    if request.method == 'POST':
        account = request.form.get('account')
        recipient_phone = request.form.get('recipient_phone', '').strip()
        amount = request.form.get('amount', '').strip()

        if account not in ['rub', 'rub2']:
            return jsonify({'success': False, 'message': 'Выберите счет'})

        if not validate_phone(recipient_phone):
            return jsonify({'success': False, 'message': 'Некорректный номер'})

        recipient_phone = normalize_phone(recipient_phone)

        if recipient_phone == current_user.phone:
            return jsonify({'success': False, 'message': 'Нельзя переводить самому себе'})

        # Проверяем получателя ДО списания — переводы только клиентам банка
        recipient = get_user_by_phone(recipient_phone)
        if not recipient:
            return jsonify({'success': False, 'message': 'Получатель не является клиентом банка'})

        try:
            amount = float(amount)
        except ValueError:
            return jsonify({'success': False, 'message': 'Некорректная сумма'})

        if amount <= 0:
            return jsonify({'success': False, 'message': 'Некорректная сумма'})

        if amount > user['accounts'][account]:
            return jsonify({'success': False, 'message': 'Недостаточно средств'})

        now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

        # Списываем у отправителя
        user['accounts'][account] -= amount
        user.setdefault('transactions', [])
        user['transactions'].append({
            'date': now_str,
            'amount': amount,
            'type': 'debit',
            'recipient_phone': recipient_phone
        })
        update_user(user)

        # Зачисляем получателю
        recipient.setdefault('accounts', {})
        recipient['accounts'][account] = recipient['accounts'].get(account, 0) + amount
        recipient.setdefault('transactions', [])
        recipient['transactions'].append({
            'date': now_str,
            'amount': amount,
            'type': 'credit',
            'from_phone': current_user.phone
        })
        update_user(recipient)

        return jsonify({'success': True, 'message': 'Перевод выполнен успешно'})

    return render_template('cabinet/transfer.html', user=user)


@cabinet_bp.route('/payments')
@login_required
def payments():
    user = _get_current_user_data()
    transactions = user.get('transactions', [])
    from datetime import datetime
    now = datetime.now()
    monthly_spent = sum(
        float(t.get('amount', 0))
        for t in transactions
        if t.get('type') == 'debit'
        and t.get('date', '').startswith(f"{now.year}-{now.month:02d}")
    )
    return render_template('cabinet/payments.html', user=user, monthly_spent=monthly_spent)


@cabinet_bp.route('/autopayments/add', methods=['POST'])
@login_required
def autopayments_add():
    user = _get_current_user_data()

    phone = (request.form.get('phone') or '').strip()
    amount = (request.form.get('amount') or '').strip()
    date_str = (request.form.get('date') or '').strip()

    if not validate_phone(phone):
        return jsonify({'success': False, 'message': 'Некорректный номер получателя'})

    phone = normalize_phone(phone)

    if phone == current_user.phone:
        return jsonify({'success': False, 'message': 'Нельзя указывать свой номер телефона'})

    if not get_user_by_phone(phone):
        return jsonify({'success': False, 'message': 'Получатель не найден в базе банка'})

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Некорректная сумма'})

    if not date_str:
        return jsonify({'success': False, 'message': 'Укажите дату автоплатежа'})

    try:
        parsed = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        if parsed < datetime.date.today():
            return jsonify({'success': False, 'message': 'Дата не может быть в прошлом'})
        display_date = parsed.strftime('%d.%m.%Y')
    except ValueError:
        return jsonify({'success': False, 'message': 'Некорректная дата'})

    user.setdefault('autopayments', [])
    user['autopayments'].append({
        'phone': phone,
        'amount': amount_val,
        'date': display_date,
        'date_iso': date_str
    })
    update_user(user)

    return jsonify({'success': True, 'message': 'Автоплатёж добавлен'})


@cabinet_bp.route('/autopayments/list')
@login_required
def autopayments_list():
    user = _get_current_user_data()
    return jsonify({'payments': user.get('autopayments', [])})


@cabinet_bp.route('/autopayments/edit', methods=['PATCH'])
@login_required
def autopayments_edit():
    user = _get_current_user_data()

    try:
        idx = int(request.form.get('index'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Неверный индекс'})

    autopayments = user.get('autopayments', [])
    if idx < 0 or idx >= len(autopayments):
        return jsonify({'success': False, 'message': 'Автоплатёж не найден'})

    field = request.form.get('field')
    value = (request.form.get('value') or '').strip()

    if field == 'amount':
        try:
            val = float(value)
            if val <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Некорректная сумма'})
        autopayments[idx]['amount'] = val

    elif field == 'date':
        try:
            parsed = datetime.datetime.strptime(value, '%Y-%m-%d').date()
            if parsed < datetime.date.today():
                return jsonify({'success': False, 'message': 'Дата не может быть в прошлом'})
            autopayments[idx]['date'] = parsed.strftime('%d.%m.%Y')
            autopayments[idx]['date_iso'] = value
        except ValueError:
            return jsonify({'success': False, 'message': 'Некорректная дата'})
    else:
        return jsonify({'success': False, 'message': 'Недопустимое поле'})

    user['autopayments'] = autopayments
    update_user(user)
    return jsonify({'success': True, 'message': 'Сохранено'})


@cabinet_bp.route('/autopayments/delete', methods=['DELETE'])
@login_required
def autopayments_delete():
    user = _get_current_user_data()

    try:
        idx = int(request.form.get('index'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Неверный индекс'})

    autopayments = user.get('autopayments', [])
    if idx < 0 or idx >= len(autopayments):
        return jsonify({'success': False, 'message': 'Автоплатёж не найден'})

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


@cabinet_bp.route('/cashback', methods=['GET', 'POST'])
@login_required
def cashback():
    user = _get_current_user_data()
    selected = user.get('cashback_categories', [])
    message = None
    success = False

    if request.method == 'POST':
        chosen = request.form.getlist('categories')
        valid_keys = set(CASHBACK_CATEGORIES.keys())
        chosen = [c for c in chosen if c in valid_keys]

        if len(chosen) != 3:
            message = 'Необходимо выбрать ровно 3 категории'
        else:
            user['cashback_categories'] = chosen
            update_user(user)
            selected = chosen
            message = 'Категории кэшбэка сохранены'
            success = True

    return render_template(
        'cabinet/cashback.html',
        selected=selected,
        message=message,
        success=success
    )


@cabinet_bp.route('/transfer/success')
@login_required
def transfer_success():
    from flask import render_template
    return render_template('cabinet/transfer_success.html')
