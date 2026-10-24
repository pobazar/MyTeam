# Приёмка МАЙТИМ

Дата: 24 октября 2026 года. PR #17–#31 слиты в main по разрешению владельца.

## Фактически проверено

- Frontend GitHub Pages: https://pobazar.github.io/MyTeam/ — build `built`, index/CSS/JS отвечают 200.
- Backend Render https://myteam-web.onrender.com — новая версия `live`, health/live и health/ready отвечают 200. CORS bridge выдаёт сессию только разрешённому Pages origin.
- На production страница входа показывает код, CSRF-защищённый polling без подтверждения остаётся authenticated=false. Telegram webhook принимает message и callback_query. Реальный новый callback пользователя не подменяется тестовым запросом.
- 40 тестов PostgreSQL и GitHub CI проходят: два недельных цикла, отсутствие автозаписи, повторы/одновременные scheduler и worker, ручная правка/пауза/повреждение черновика, feedback, ачивки, аналитика, nonce/подтверждение и чужой callback, CORS/CSRF, сессия без cross-site cookies.
- Миграция 0001→0004 на данных сохраняет профиль, историю, feedback и ачивку. Проверены INSERT старого приложения благодаря DB defaults.
- Локальный Chromium 375/1280: код, ожидание подтверждения, автоматический переход, онбординг/профиль, отказ сети с сохранением ввода, повтор, выход. Изолированная SQLite и имитация Telegram; настоящие получатели не участвуют.
- Отдельный pg_dump/pg_restore проверен в локальных PostgreSQL-базах: 2 профиля, 4 записи истории, 1 ответ, 1 ачивка; UUID и контрольные суммы снимков/комментариев совпали. Production этим тестом не изменялась.
- Telegram @artemiy_mikhaylov активировал бота; getChat и сохранённая успешная private-доставка подтвердили user/chat ID 776767993. OWNER_TELEGRAM_ID/OWNER_CHAT_ID заданы в Render. Серверные ключи не находятся в коде/статическом клиенте.
- Supabase схема myteam закрыта от PostgREST (exposed: public,graphql_public). Storage list buckets отвечает 200, buckets отсутствуют; загрузки файлов MVP не использует и они не проверялись.

## Что блокирует недельную автоматику

Создание единственного cron `myteam-cycle` на минимальном Starter согласовано владельцем. Конфигурация: */5 * * * * UTC, `python manage.py tick --delivery-limit 100 && python manage.py monitor`. Render вернул HTTP 402: Payment information is required; провайдер требует карту в workspace с MyTeam (https://dashboard.render.com/billing). Пополненный баланс сам по себе не позволил создать сервис. Повторное согласование расходов не нужно.

Cron-сервис фактически не создан. Его реальные запуски не проверены, heartbeat отсутствует, /health/operations честно показывает scheduler_stale. Недельный цикл не объявляется запущенным. После исправления Billing повторить создание, дождаться успешной реальной обработки без подмены времени и проверить heartbeat/доставку. По документации Render — минимум $1 в месяц на cron плюс фактическое посекундное использование, не обещание фиксированного счёта.

## Внешний контроль и отложенные проверки

Владелец вручную добавляет GitHub Actions Secrets: MYTEAM_OPS_SECRET из Render OPS_SECRET; MYTEAM_TG_BOT_TOKEN из TG_BOT_TOKEN; MYTEAM_OWNER_CHAT_ID=776767993. Variables: MYTEAM_PUBLIC_URL=https://myteam-web.onrender.com, MYTEAM_MONITOR_ENABLED=true после запуска cron. Текущая интеграция GitHub получает 403 при чтении/записи Secrets/Variables, их конфигурация не подтверждена. До успешного реального workflow watchdog не считается включённым.

Реальная проверка контактов двух аккаунтов без username отложена владельцем. Модульные проверки прав и inline-ссылок выполнены. Тестовые расписание и рассылки никогда не прогоняются на настоящих участниках.

Ограничения: free Render может просыпаться/переключаться долго; один rollout занял около 8 минут с таймаутами, потери БД не наблюдалось. Внешний Chromium в cloud не доверяет сертификату egress proxy: TLS не отключался, production HTTP-проверки проводились клиентом с верификацией TLS. Ресурсные квоты не предполагаются доступными программно; pg_database_size доступен, порог DB_WARNING_BYTES оператор задаёт по тарифу. Подбор больших нечётных когорт и консервативное сопоставление команд описаны в operations.md.
