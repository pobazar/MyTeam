# МАЙТИМ

Добровольные знакомства коллег. Активности: Random Coffee, Code Names и GeoGuesser. На каждый раунд нужна отдельная запись.

Python 3.12+, Django 5.2, PostgreSQL 16 (Supabase), JSON API и статический интерфейс Pages. Render запускает Gunicorn; фоновые команды работают отдельно от посещений сайта.

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
python manage.py tick --event prepare  # только подготовка; остальные: publish, feedback, invite
python manage.py deliver
python manage.py monitor
```

`tick` запускается GitHub Actions через защищённый OIDC endpoint, а не посещениями сайта. Четыре события МСК: вторник 09:00 (ОС), вторник 21:00 (закрытие + подготовка), среда 09:00 (публикация), четверг 09:00 (приглашение не записавшимся). GitHub Secrets для расписания не нужны. Без `SEND_TELEGRAM=true` плановые рассылки не отправляются. Вход и запрос контактов — добровольные действия пользователя, ответ бота на них отправляется сразу. Тесты никогда не используют production БД или реальные Telegram chat ID.

[Операции, миграции, восстановление, пауза и получатель](docs/technical/operations.md) · [фактические проверки и оставшиеся ограничения](docs/technical/acceptance.md).

## Веб на GitHub Pages

Основной адрес: https://pobazar.github.io/MyTeam/. Pages отдаёт весь статический интерфейс (`index.html`, `web/app.js`, `web/tokens.css`, `web/app.css`), Render — [JSON API](docs/technical/api.md), без загрузки HTML страниц. Главный экран — активности; история и профиль открываются отдельными экранами, оценка — диалогом. Каркас и загрузка видны до ответа API, ошибки предлагают повтор. Подтверждённая сессия хранится в localStorage как непрозрачный идентификатор Django и доступна вкладкам одного браузера; неподтверждённый вход остаётся в sessionStorage, серверные ключи остаются в Render. CORS ограничен Pages origin, POST защищены CSRF с серверным хранением. Legacy HTML маршруты сохранены только старым вкладкам.

Локально запустить два процесса:

```sh
python manage.py runserver 127.0.0.1:8000
python scripts/serve_pages.py
```

`serve_pages.py` подставляет только локальный API и не обращается к production. Вход: код на странице → открыть бота → сверить код и нажать «Подтвердить вход» в чате → автоматический переход при возвращении. Первому пользователю Telegram может потребоваться нажать «Старт». Истёкший код не подтверждает вход; новый создаётся на странице. Обычный `/start` без нажатия подтверждения не авторизует браузер.

Незалогиненный сайт всегда начинает с трёх статических шагов онбординга. Только затем явно запрашивается Telegram-код, после входа обязателен профиль. Logout сразу возвращает к введению и отзывает серверную сессию в фоне, без редиректа на код.

Актуальные дизайн-гайдлайны и платформенная адаптация: [design.md](docs/technical/design.md).

Скриншоты и галереи не храним в публичном репозитории. Локальные прогоны: `scripts/qa/review-browser.cjs`, `scripts/qa/codenames-browser.cjs`; сборка локальной галереи: `scripts/qa/build-review.py`. Результаты сохраняются за пределами репозитория.

GeoGuesser: [правила группировки, совместная игра и достижение](docs/technical/geoguesser.md).
