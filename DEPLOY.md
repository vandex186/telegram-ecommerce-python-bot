# Запуск бота 24/7

**Важно:** код на GitHub **не** запускает бота. GitHub хранит исходники. Пока бот крутится только через `./run.sh` на Mac — он жив, пока жив процесс. Закрыл терминал / выключил Mac → бот молчит.

Чтобы работал круглосуточно: задеплой **Background Worker** на Render / Railway / VPS (ниже). Репозиторий: [vandex186/telegram-ecommerce-python-bot](https://github.com/vandex186/telegram-ecommerce-python-bot) (ветка `main`).

## Почему локально «всё ок», а «с GitHub» — нет

| Где | Что происходит |
|-----|----------------|
| **Локально** | `./run.sh` → процесс `python bot.py` на твоём Mac, база `orders.db` с форвардами/постами канала |
| **Только GitHub** | Код лежит в репозитории, **никто его не исполняет** |
| **Render / VPS** | Тот же код крутится на сервере 24/7; секреты задаёшь в Environment Variables |

После `git push` на сервере нужен **Redeploy** (или auto-deploy из GitHub), иначе на хосте останется старая версия.

## Как перезапустить локально

```bash
cd /Users/mac/Desktop/telegrambot/telegram-ecommerce-python-bot
# остановить старый процесс, затем:
./run.sh
```

Или в Cursor/терминале: Ctrl+C → снова `./run.sh`.

При старте в логе должно быть: `Telegram API OK` и `Application started`.

## Pending updates (сброс при старте)

Telegram копит сообщения боту, пока процесс **не** слушает API (`getUpdates`).

В коде при старте:

```python
app.run_polling(drop_pending_updates=True)
```

Это значит: всё, что пришло **пока бот был выключен**, **не обрабатывается** (форварды каталога, /start и т.д.). Нужно **отправить / форварднуть снова** уже после `Application started`.

Зачем сбрасывать: иначе после долгого даунтайма бот «догоняет» сотни старых апдейтов и может вести себя странно.

## Автосинхронизация каталога (вместо ручного `/sync_catalog`)

Пока бот **запущен** (локально или на Render):

1. Новые/изменённые посты канала (бот = админ) → сразу в кэш.
2. Форвард админом в личку → кэш + sync.
3. **Таймер** `CATALOG_SYNC_INTERVAL_MINUTES` (по умолчанию `15`) → тот же полный sync, что `/sync_catalog`, без APScheduler.

В `.env` / Environment:

```env
CATALOG_SYNC_INTERVAL_MINUTES=15
CATALOG_SYNC_POST_LIMIT=100
```

`0` = таймер выключен.

CLI для cron / Cursor agent (нужен доступ к **той же** `orders.db`, что у живого бота):

```bash
.venv/bin/python sync_catalog_cli.py --limit 100
```

Отдельный GitHub Actions cron **без** общей БД с ботом бесполезен: sync только перечитывает уже закэшированные посты.

## Что нужно перед деплоем

1. Токен бота от [@BotFather](https://t.me/BotFather).
2. Переменные из `.env.example` (на хостинге — Environment Variables, не файл в git).
3. Бот — **админ** в приватном канале каталога; `STOCK_CHANNEL_ID` задан.
4. (Опционально) API-ключ OxaPay для оплаты.

Секреты **не** коммитьте в Git.

## Вариант A — Render (простой старт)

1. Запушьте код на GitHub (форк `vandex186/...`).
2. [render.com](https://render.com) → **New** → **Background Worker**.
3. Подключите репозиторий, ветку **`main`**.
4. **Build command:** `pip install -r requirements.txt && (pip uninstall -y apscheduler || true)`
5. **Start command:** `python bot.py`
6. В **Environment** добавьте:
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_USER_ID`
   - `STOCK_CHANNEL_ID`
   - `CATALOG_SYNC_POST_LIMIT` = `100`
   - `CATALOG_SYNC_INTERVAL_MINUTES` = `15`
7. Deploy.

В репозитории есть `render.yaml` — можно импортировать Blueprint.

**Важно:** на Render останови локальный `./run.sh`, иначе будет `409 Conflict` (два процесса с одним токеном).

## Вариант B — Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub.
2. Выберите репозиторий и ветку `main`.
3. Start: `python bot.py`.
4. Variables: те же, что в `.env.example`.

## Вариант C — VPS (Linux)

```bash
git clone https://github.com/vandex186/telegram-ecommerce-python-bot.git
cd telegram-ecommerce-python-bot
cp .env.example .env   # заполните TELEGRAM_BOT_TOKEN, STOCK_CHANNEL_ID, ADMIN_USER_ID
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip uninstall -y apscheduler || true
```

Systemd (`/etc/systemd/system/telegram-bot.service`):

```ini
[Unit]
Description=Telegram Ecommerce Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram-ecommerce-python-bot
Environment=TZ=UTC
EnvironmentFile=/home/ubuntu/telegram-ecommerce-python-bot/.env
ExecStart=/home/ubuntu/telegram-ecommerce-python-bot/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

## Docker

```bash
docker build -t telegram-ecommerce-bot .
docker run -d --name tg-bot --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=your_token \
  -e ADMIN_USER_ID=your_id \
  -e STOCK_CHANNEL_ID=-100... \
  -e CATALOG_SYNC_INTERVAL_MINUTES=15 \
  telegram-ecommerce-bot
```

## После деплоя — каталог

1. Бот = админ канала.
2. Перешлите AVAILABLE + карточки боту в личку (с аккаунта `ADMIN_USER_ID`) **или** дождитесь новых постов в канале.
3. `/sync_catalog` при необходимости; дальше сработает таймер.

Локально для теста: `./run.sh` (нужен открытый терминал / процесс).
