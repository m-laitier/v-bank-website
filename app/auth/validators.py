import re
import string


FULL_NAME_REGEX = r'^[А-Яа-яЁё -]{1,100}$'
PHONE_REGEX = r'^(\+7|8)\d{10}$'


def validate_full_name(full_name):
    return bool(
        re.fullmatch(
            FULL_NAME_REGEX,
            full_name
        )
    )


def validate_phone(phone):
    return bool(
        re.fullmatch(
            PHONE_REGEX,
            phone
        )
    )


def normalize_phone(phone):
    if phone.startswith('8'):
        return '+7' + phone[1:]

    return phone


def validate_password(password):
    if len(password) < 5 or len(password) > 25:
        return False

    allowed_symbols = (
        string.ascii_letters +
        string.digits +
        string.punctuation
    )

    return all(
        symbol in allowed_symbols
        for symbol in password
    )