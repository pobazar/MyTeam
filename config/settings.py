import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
import dj_database_url
BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = os.getenv('APP_ENV', 'development') == 'production'
SECRET_KEY = os.getenv('SECRET_KEY', 'local-development-only-not-for-deployment')
if PRODUCTION:
    missing = [k for k in ('SECRET_KEY', 'DATABASE_URL', 'TG_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME', 'PUBLIC_URL', 'TELEGRAM_WEBHOOK_SECRET') if not os.getenv(k)]
    if len(SECRET_KEY)<50:
        missing.append('SECRET_KEY (minimum 50 characters)')
    if missing:
        raise ImproperlyConfigured('Missing required configuration: ' + ', '.join(missing))
DEBUG = not PRODUCTION
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.staticfiles', 'myteam']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'myteam.views.public_settings']}}]
DATABASES = {'default': dj_database_url.config(default='sqlite:///' + str(BASE_DIR / 'local.sqlite3'), conn_max_age=60, ssl_require=PRODUCTION)}
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage' if PRODUCTION else 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 2592000 if PRODUCTION else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', '')
TELEGRAM_WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
PUBLIC_URL = os.getenv('PUBLIC_URL', 'http://127.0.0.1:8000').rstrip('/')
OWNER_TELEGRAM_ID = os.getenv('OWNER_TELEGRAM_ID', '')
OWNER_CHAT_ID = os.getenv('OWNER_CHAT_ID', '')
FEEDBACK_HOUR = int(os.getenv('FEEDBACK_HOUR', '12'))
FEEDBACK_MINUTE = int(os.getenv('FEEDBACK_MINUTE', '0'))
SEND_TELEGRAM = os.getenv('SEND_TELEGRAM', 'false').lower() == 'true'
OPS_SECRET = os.getenv('OPS_SECRET', '')
DB_WARNING_BYTES = int(os.getenv('DB_WARNING_BYTES', '0'))
CSRF_FAILURE_VIEW = 'myteam.views.csrf_failure'
LOGGING = {'version':1,'disable_existing_loggers':False,'handlers':{'null':{'class':'myteam.logging.SafeErrorHandler'}},'loggers':{'django.request':{'handlers':['null'],'propagate':False},'django.server':{'handlers':['null'],'propagate':False}}}
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
