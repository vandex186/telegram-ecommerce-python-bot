# Запуск бота 24/7

**Важно:** размещение кода на GitHub **не** держит бота онлайн. GitHub — это хранилище и версии. Чтобы бот отвечал круглосуточно, запустите `bot.py` на сервере или в облаке (worker-процесс).

## Что нужно перед деплоем

1. Токен бота от [@BotFather](https://t.me/BotFather).
2. Файл `config.py` (из `config.example.py`) **или** переменные окружения (см. `.env.example`).
3. Для ветки `catalog/channel-cards`: бот — админ в приватном канале, `STOCK_CHANNEL_ID` в конфиге.
4. (Опционально) API-ключ OxaPay для оплаты.

Секреты **не** коммитьте в Git: только `.env` локально или переменные в панели хостинга.

## Вариант A — Render (простой старт)

1. Залейте репозиторий на GitHub (форк или оригинал).
2. [render.com](https://render.com) → **New** → **Background Worker**.
3. Подключите репозиторий, ветку (`catalog/channel-cards` или `catalog/inline-buttons`).
4. **Build command:** `pip install -r requirements.txt`
5. **Start command:** `python bot.py`
6. В **Environment** добавьте:
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_USER_ID`
   - `STOCK_CHANNEL_ID` (только для channel-cards)
7. Deploy.

В репозитории есть `render.yaml` — можно импортировать Blueprint.

## Вариант B — Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub.
2. Выберите репозиторий и ветку.
3. Start: `python bot.py` (или `bash run.sh`).
4. Variables: те же, что в `.env.example`.

## Вариант C — VPS (Linux)

```bash
git clone https://github.com/YOUR_USERNAME/telegram-ecommerce-python-bot.git
cd telegram-ecommerce-python-bot
git checkout catalog/channel-cards   # или catalog/inline-buttons
cp config.example.py config.py      # отредактируйте
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
  -e ADMIN_USER_ID=123456789 \
  telegram-ecommerce-bot
```

## Проверка

- В логах: `Application started`.
- В Telegram: `/start` → Shop.
- Только **один** процесс на один токен (иначе `409 Conflict`).

## Обновление с GitHub

На VPS:

```bash
cd telegram-ecommerce-python-bot
git pull
sudo systemctl restart telegram-bot
```

На Render/Railway — обычно автодеплой при push в выбранную ветку.
