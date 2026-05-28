import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'super-secret-key')
    WTF_CSRF_ENABLED = True
