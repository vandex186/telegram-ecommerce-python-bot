# Запуск бота 24/7

**Важно:** код на GitHub **не** запускает бота. Пока открыт только терминал на Mac — бот живёт, пока работает `./run.sh`. Закрыл терминал / выключил Mac → бот молчит.

Чтобы работал круглосуточно: задеплой worker на Render / Railway / VPS (ниже). Репозиторий: [vandex186/telegram-ecommerce-python-bot](https://github.com/vandex186/telegram-ecommerce-python-bot) (ветка `main`).

## Что нужно перед деплоем

1. Токен бота от [@BotFather](https://t.me/BotFather).
2. Переменные из `.env.example` (на хостинге — Environment Variables, не файл в git).
3. Бот — **админ** в приватном канале каталога; `STOCK_CHANNEL_ID` задан.
4. (Опционально) API-ключ OxaPay для оплаты.

Секреты **не** коммитьте в Git.

## Вариант A — Render (простой старт)

1. Залейте / запушьте код на GitHub (ваш форк).
2. [render.com](https://render.com) → **New** → **Background Worker**.
3. Подключите репозиторий, ветку **`main`**.
4. **Build command:** `pip install -r requirements.txt && (pip uninstall -y apscheduler || true)`
5. **Start command:** `python bot.py`
6. В **Environment** добавьте:
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_USER_ID`
   - `STOCK_CHANNEL_ID`
   - `CATALOG_SYNC_POST_LIMIT` = `100` (опционально)
7. Deploy.

В репозитории есть `render.yaml` — можно импортировать Blueprint.

## Вариант B — Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub.
2. Выберите репозиторий и ветку `main`.
3. Start: `python bot.py` (или `bash run.sh`).
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
  telegram-ecommerce-bot
```

## После деплоя — каталог

1. Бот = админ канала.
2. Перешлите AVAILABLE + карточки боту в личку (с аккаунта `ADMIN_USER_ID`) **или** дождитесь новых постов в канале.
3. `/sync_catalog` в личке с ботом.

Локально для теста: `./run.sh` (нужен открытый терминал).
