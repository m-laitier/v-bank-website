import json
import os

import requests


TOKEN_FILE = '.api_client_tokens.json'
DEFAULT_BASE_URL = 'http://127.0.0.1:5000'
SESSION = requests.Session()
SESSION.trust_env = False


def _load_tokens():
    if not os.path.exists(TOKEN_FILE):
        return {}
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_tokens(tokens):
    with open(TOKEN_FILE, 'w', encoding='utf-8') as file:
        json.dump(tokens, file, ensure_ascii=False, indent=2)


def _api_request(base_url, method, path, token=None, payload=None):
    url = f"{base_url.rstrip('/')}{path}"
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    print(f'\n>>> {method.upper()} {url}')

    try:
        response = SESSION.request(
            method=method,
            url=url,
            headers=headers,
            json=payload,
            timeout=10
        )
    except requests.RequestException as error:
        return {'success': False, 'message': f'Ошибка подключения: {error}'}, None

    try:
        data = response.json()
    except ValueError:
        print(f'HTTP {response.status_code}: {response.text}')
        return None, response.status_code

    return data, response.status_code


def _print_result(data, status_code):
    if status_code is None:
        print('HTTP статус: ERROR')
    else:
        print(f'HTTP статус: {status_code}')
    if data is None:
        print('Пустой ответ')
        return
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _prompt_non_empty(label):
    while True:
        value = input(label).strip()
        if value:
            return value
        print('Поле не может быть пустым')


def _pause():
    input('\nНажмите Enter, чтобы продолжить...')


def _check_api(base_url):
    data, code = _api_request(base_url, 'GET', '/')
    _print_result(data, code)


def _register_user(base_url, tokens):
    full_name = _prompt_non_empty('ФИО: ')
    phone = _prompt_non_empty('Телефон: ')
    password = _prompt_non_empty('Пароль: ')
    data, code = _api_request(
        base_url,
        'POST',
        '/api/auth/register',
        payload={'full_name': full_name, 'phone': phone, 'password': password}
    )
    if data and data.get('success') and data.get('token'):
        tokens['user_token'] = data['token']
        _save_tokens(tokens)
    _print_result(data, code)


def _login_user(base_url, tokens):
    phone = _prompt_non_empty('Телефон: ')
    password = _prompt_non_empty('Пароль: ')
    data, code = _api_request(
        base_url,
        'POST',
        '/api/auth/login',
        payload={'phone': phone, 'password': password}
    )
    if data and data.get('success') and data.get('token'):
        tokens['user_token'] = data['token']
        _save_tokens(tokens)
    _print_result(data, code)


def _user_menu(base_url, tokens):
    while True:
        print('\nЛИЧНЫЙ КАБИНЕТ')
        print('1. Обзор кабинета')
        print('2. Просмотр трат')
        print('3. Перевод по номеру')
        print('4. Автоплатежи')
        print('5. Категории кэшбэка')
        print('6. Профиль')
        print('0. Назад')
        choice = input('\nВыберите действие: ').strip()

        if choice == '1':
            data, code = _api_request(base_url, 'GET', '/api/cabinet', token=tokens.get('user_token'))
            _print_result(data, code)
            _pause()
        elif choice == '2':
            data, code = _api_request(base_url, 'GET', '/api/payments', token=tokens.get('user_token'))
            _print_result(data, code)
            _pause()
        elif choice == '3':
            account = _prompt_non_empty('Счет (rub/rub2): ')
            recipient_phone = _prompt_non_empty('Телефон получателя: ')
            amount_raw = _prompt_non_empty('Сумма: ')
            try:
                amount = float(amount_raw)
            except ValueError:
                print('Некорректная сумма')
                _pause()
                continue
            data, code = _api_request(
                base_url,
                'POST',
                '/api/transfer',
                token=tokens.get('user_token'),
                payload={
                    'account': account,
                    'recipient_phone': recipient_phone,
                    'amount': amount
                }
            )
            _print_result(data, code)
            _pause()
        elif choice == '4':
            _autopayments_menu(base_url, tokens)
        elif choice == '5':
            _cashback_menu(base_url, tokens)
        elif choice == '6':
            _profile_menu(base_url, tokens)
        elif choice == '0':
            return
        else:
            print('Неизвестная команда')


def _autopayments_menu(base_url, tokens):
    while True:
        print('\nАВТОПЛАТЕЖИ')
        print('1. Показать автоплатежи')
        print('2. Добавить автоплатеж')
        print('3. Изменить автоплатеж')
        print('4. Удалить автоплатеж')
        print('0. Назад')
        choice = input('\nВыберите действие: ').strip()

        if choice == '1':
            data, code = _api_request(base_url, 'GET', '/api/autopayments/list', token=tokens.get('user_token'))
            _print_result(data, code)
            _pause()
        elif choice == '2':
            phone = _prompt_non_empty('Телефон получателя: ')
            amount_raw = _prompt_non_empty('Сумма: ')
            date_iso = _prompt_non_empty('Дата (DD-MM-YYYY): ')
            try:
                amount = float(amount_raw)
            except ValueError:
                print('Некорректная сумма')
                _pause()
                continue
            data, code = _api_request(
                base_url,
                'POST',
                '/api/autopayments/add',
                token=tokens.get('user_token'),
                payload={'phone': phone, 'amount': amount, 'date': date_iso}
            )
            _print_result(data, code)
            _pause()
        elif choice == '3':
            index_raw = _prompt_non_empty('Индекс автоплатежа: ')
            field = _prompt_non_empty('Поле (amount/date): ')
            if field == 'date':
                print('Дата вводится в формате DD-MM-YYYY')
            value = _prompt_non_empty('Новое значение: ')
            try:
                index = int(index_raw)
            except ValueError:
                print('Некорректный индекс')
                _pause()
                continue
            data, code = _api_request(
                base_url,
                'PATCH',
                '/api/autopayments/edit',
                token=tokens.get('user_token'),
                payload={
                    'index': index,
                    'field': field,
                    'value': value
                }
            )
            _print_result(data, code)
            _pause()
        elif choice == '4':
            index_raw = _prompt_non_empty('Индекс автоплатежа: ')
            try:
                index = int(index_raw)
            except ValueError:
                print('Некорректный индекс')
                _pause()
                continue
            data, code = _api_request(
                base_url,
                'DELETE',
                '/api/autopayments/delete',
                token=tokens.get('user_token'),
                payload={'index': index}
            )
            _print_result(data, code)
            _pause()
        elif choice == '0':
            return
        else:
            print('Неизвестная команда')


def _cashback_menu(base_url, tokens):
    while True:
        print('\nКЭШБЭК')
        print('1. Показать текущие категории')
        print('2. Выбрать категории (ровно 3)')
        print('0. Назад')
        choice = input('\nВыберите действие: ').strip()

        if choice == '1':
            data, code = _api_request(base_url, 'GET', '/api/cashback', token=tokens.get('user_token'))
            _print_result(data, code)
            _pause()
        elif choice == '2':
            print('Введите 3 категории через запятую, например: all,restaurants,travel')
            categories_raw = _prompt_non_empty('Категории: ')
            categories = [item.strip() for item in categories_raw.split(',') if item.strip()]
            data, code = _api_request(
                base_url,
                'POST',
                '/api/cashback',
                token=tokens.get('user_token'),
                payload={'categories': categories}
            )
            _print_result(data, code)
            _pause()
        elif choice == '0':
            return
        else:
            print('Неизвестная команда')


def _profile_menu(base_url, tokens):
    while True:
        print('\nПРОФИЛЬ')
        print('1. Показать профиль')
        print('2. Изменить номер телефона')
        print('3. Изменить пароль')
        print('0. Назад')
        choice = input('\nВыберите действие: ').strip()

        if choice == '1':
            data, code = _api_request(base_url, 'GET', '/api/profile', token=tokens.get('user_token'))
            _print_result(data, code)
            _pause()
        elif choice == '2':
            phone = _prompt_non_empty('Новый номер телефона: ')
            data, code = _api_request(
                base_url,
                'POST',
                '/api/profile/change-phone',
                token=tokens.get('user_token'),
                payload={'phone': phone}
            )
            _print_result(data, code)
            _pause()
        elif choice == '3':
            current_password = _prompt_non_empty('Текущий пароль: ')
            new_password = _prompt_non_empty('Новый пароль: ')
            repeat_password = _prompt_non_empty('Повтор нового пароля: ')
            data, code = _api_request(
                base_url,
                'POST',
                '/api/profile/change-password',
                token=tokens.get('user_token'),
                payload={
                    'current_password': current_password,
                    'new_password': new_password,
                    'repeat_password': repeat_password
                }
            )
            _print_result(data, code)
            _pause()
        elif choice == '0':
            return
        else:
            print('Неизвестная команда')


def _register_admin(base_url, tokens):
    full_name = _prompt_non_empty('ФИО админа: ')
    phone = _prompt_non_empty('Телефон админа: ')
    password = _prompt_non_empty('Пароль админа: ')
    data, code = _api_request(
        base_url,
        'POST',
        '/api/admin/register',
        payload={'full_name': full_name, 'phone': phone, 'password': password}
    )
    if data and data.get('success') and data.get('token'):
        tokens['admin_token'] = data['token']
        _save_tokens(tokens)
    _print_result(data, code)


def _login_admin(base_url, tokens):
    phone = _prompt_non_empty('Телефон админа: ')
    password = _prompt_non_empty('Пароль админа: ')
    data, code = _api_request(
        base_url,
        'POST',
        '/api/admin/login',
        payload={'phone': phone, 'password': password}
    )
    if data and data.get('success') and data.get('token'):
        tokens['admin_token'] = data['token']
        _save_tokens(tokens)
    _print_result(data, code)


def _admin_menu(base_url, tokens):
    while True:
        print('\nADMIN-МЕНЮ')
        print('1. Показать всех пользователей')
        print('2. Создать пользователя через API')
        print('3. Удалить пользователя по ID')
        print('0. Назад')
        choice = input('\nВыберите действие: ').strip()

        if choice == '1':
            data, code = _api_request(
                base_url,
                'GET',
                '/api/admin/users',
                token=tokens.get('admin_token')
            )
            _print_result(data, code)
            _pause()
        elif choice == '2':
            full_name = _prompt_non_empty('ФИО: ')
            phone = _prompt_non_empty('Телефон: ')
            password = _prompt_non_empty('Пароль: ')
            data, code = _api_request(
                base_url,
                'POST',
                '/api/admin/users',
                token=tokens.get('admin_token'),
                payload={'full_name': full_name, 'phone': phone, 'password': password}
            )
            _print_result(data, code)
            _pause()
        elif choice == '3':
            user_id = _prompt_non_empty('ID пользователя: ')
            data, code = _api_request(
                base_url,
                'DELETE',
                f'/api/admin/users/{user_id}',
                token=tokens.get('admin_token')
            )
            _print_result(data, code)
            _pause()
        elif choice == '0':
            return
        else:
            print('Неизвестная команда')


def main():
    tokens = _load_tokens()
    print('=== Консольный клиент для WSGI/Flask REST API ===')
    base_url = DEFAULT_BASE_URL

    while True:
        print('\nГЛАВНОЕ МЕНЮ API-КЛИЕНТА:')
        print('1. Проверить API')
        print('2. Зарегистрироваться')
        print('3. Войти')
        print('4. Личный кабинет')
        print('5. Создать администратора')
        print('6. Войти как администратор')
        print('7. Admin-меню')
        print('0. Выход')
        choice = input('\nВыберите действие: ').strip()

        if choice == '1':
            _check_api(base_url)
            _pause()
        elif choice == '2':
            _register_user(base_url, tokens)
            _pause()
        elif choice == '3':
            _login_user(base_url, tokens)
            _pause()
        elif choice == '4':
            _user_menu(base_url, tokens)
        elif choice == '5':
            _register_admin(base_url, tokens)
            _pause()
        elif choice == '6':
            _login_admin(base_url, tokens)
            _pause()
        elif choice == '7':
            _admin_menu(base_url, tokens)
        elif choice == '0':
            print('Выход')
            return
        else:
            print('Неизвестная команда')


if __name__ == '__main__':
    main()
