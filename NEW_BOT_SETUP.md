# Настройка нового Telegram-бота TetraHydro

Проект: `telegram-ecommerce-python-bot`  
Старый бот (остановить перед запуском нового): [@streettrader_bot](https://t.me/streettrader_bot)  
**Новый бот:** [@TetraHydroGuild_bot](https://t.me/TetraHydroGuild_bot)

Один и тот же код не должен одновременно работать со старым и новым токеном — сначала остановите старый процесс.

---

## 1. Создать бота в BotFather

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте команду `/newbot`.
3. **Display name** (отображаемое имя): `TetraHydro`
4. **Username** (логин бота): `TetraHydroGuild_bot`  
   Username должен заканчиваться на `_bot` и быть уникальным в Telegram.
5. BotFather пришлёт **HTTP API token** — скопируйте его целиком (формат `123456789:ABCdef...`).  
   **Не публикуйте токен** в чатах, скриншотах и git.

После создания бот будет доступен по ссылке: **https://t.me/TetraHydroGuild_bot**

---

## 2. Вставить токен в `.env`

Файл `.env` уже может существовать — **не удаляйте и не перезаписывайте его целиком**.

Рекомендуется сделать резервную копию:

```bash
cp .env .env.backup.$(date +%Y%m%d)
```

Затем откройте `.env` и замените **только** строку с токеном:

```env
TELEGRAM_BOT_TOKEN=ваш_новый_токен_из_BotFather
```

Остальные переменные (`STOCK_CHANNEL_ID`, `ADMIN_USER_ID` и т.д.) **оставьте как есть**, если канал каталога и админ не менялись.

Шаблон для справки: `.env.example` или `.env.newbot.example`.

---

## 3. Остановить старый бот

Перед запуском **@TetraHydroGuild_bot** остановите **@streettrader_bot**:

- Найдите терминал, где запущен `./run.sh` или `python bot.py`.
- Нажмите **Ctrl+C**.

Два процесса polling из одной папки не нужны — работает только тот, чей токен в `.env`.

---

## 4. Добавить @TetraHydroGuild_bot в канал каталога

Магазин читает товары из **приватного канала** (`STOCK_CHANNEL_ID` в `.env`).

1. Откройте ваш приватный канал каталога.
2. **Настройки канала → Администраторы → Добавить администратора**
3. Найдите **@TetraHydroGuild_bot** и добавьте его.
4. Для приватного канала бот должен быть **администратором** (достаточно прав на чтение сообщений).

`STOCK_CHANNEL_ID` менять не нужно, если канал тот же. Старого @streettrader_bot из админов канала можно убрать (необязательно).

---

## 5. Запуск

```bash
cd /Users/mac/Desktop/telegrambot/telegram-ecommerce-python-bot
./run.sh
```

В Telegram откройте **https://t.me/TetraHydroGuild_bot** → `/start` → **Shop** / **Cart**.

---

## Чеклист

- [ ] `/newbot` в @BotFather → имя **TetraHydro**, username **TetraHydroGuild_bot**
- [ ] Токен вставлен в `.env` → `TELEGRAM_BOT_TOKEN`
- [ ] Старый @streettrader_bot остановлен (Ctrl+C)
- [ ] @TetraHydroGuild_bot — админ в канале каталога (`STOCK_CHANNEL_ID`)
- [ ] `./run.sh` запущен без ошибок
- [ ] Бот отвечает на `/start` по ссылке https://t.me/TetraHydroGuild_bot
