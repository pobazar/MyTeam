# МАЙТИМ

Добровольные знакомства коллег. MVP: Random Coffee. На каждый раунд нужна отдельная запись.

Python 3.12+, Django 5.2, PostgreSQL 16 (Supabase), серверные HTML-страницы. Render запускает Gunicorn; фоновые команды работают отдельно от посещений сайта.

## Локальный запуск

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Без DATABASE_URL используется локальная SQLite только для разработки; проверки конкурентности выполняются на PostgreSQL. Переменные из `.env.example` экспортируются процессу (файл автоматически не читается). Никогда не копируйте рабочие секреты в клиент или репозиторий.

```sh
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
```

Решения: [архитектура](docs/technical/architecture.md). Требования: [продукт](docs/product/mvp.md), [техника](docs/technical/requirements.md).
