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

## Эксплуатация и приёмка

```sh
python manage.py bootstrap_round
python manage.py tick
python manage.py deliver
python manage.py monitor
```

`tick` запускается отдельным внешним cron, а не посещениями сайта. Без `SEND_TELEGRAM=true` плановые рассылки не отправляются. Вход и запрос контактов — добровольные действия пользователя, ответ бота на них отправляется сразу. Тесты никогда не используют production БД или реальные Telegram chat ID.

[Операции, миграции, восстановление, пауза и получатель](docs/technical/operations.md) · [фактические проверки и оставшиеся ограничения](docs/technical/acceptance.md).
