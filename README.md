# MTProto Proxy Telegram Bot

Telegram-бот для установки и управления MTProto прокси на ваших серверах — без консоли, в один клик.

## Возможности

- **Добавление серверов** — укажите IP, SSH-логин/пароль и бот запомнит
- **Установка в один клик** — бот подключается по SSH и автоматически:
  - Устанавливает Docker
  - Скачивает и запускает [mtg](https://github.com/9seconds/mtg) прокси
  - Генерирует fake-TLS секрет
  - Открывает порт в файрволе
  - Сохраняет конфигурацию
- **Готовые ссылки** — `t.me/proxy` и `tg://proxy` для подключения
- **Управление** — статус, обновление, перезапуск, удаление прокси
- **Настройки** — порт, домен маскировки, DNS
- **Мульти-сервер** — управляйте несколькими серверами из одного бота

## Требования

- Python 3.11+
- Telegram Bot Token (от [@BotFather](https://t.me/BotFather))
- VPS/VDS с Linux и root-доступом по SSH

## Установка

```bash
# Клонируйте проект
git clone <repo-url>
cd mttgbot

# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или: venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt

# Скопируйте и заполните конфиг
cp .env.example .env
# Отредактируйте .env — укажите BOT_TOKEN и ADMIN_IDS
```

## Настройка

Отредактируйте файл `.env`:

```
BOT_TOKEN=123456:ABC-DEF...     # Токен от @BotFather
ADMIN_IDS=123456789              # Ваш Telegram ID (через запятую для нескольких)
```

## Запуск

```bash
python main.py
```

## Как пользоваться

1. Запустите бота командой `/start`
2. Нажмите **«Добавить сервер»**
3. Введите данные VPS: название, IP, SSH-порт, логин, пароль
4. Настройте параметры прокси (порт, домен маскировки)
5. Нажмите **«Установить прокси»** — бот всё сделает автоматически
6. Получите готовую ссылку — отправьте друзьям или нажмите для подключения

## Структура проекта

```
mttgbot/
├── main.py              # Точка входа
├── bot.py               # Хендлеры Telegram-бота
├── keyboards.py         # Inline-клавиатуры
├── database.py          # SQLite база данных
├── ssh_manager.py       # SSH-подключение (paramiko)
├── proxy_installer.py   # Логика установки MTProto прокси
├── config.py            # Конфигурация
├── requirements.txt     # Зависимости
├── .env.example         # Шаблон конфигурации
└── README.md
```

## Безопасность

- SSH-пароли хранятся в локальной SQLite базе
- Сообщения с паролями автоматически удаляются из чата
- Рекомендуется использовать SSH-ключи вместо паролей
- Для продакшена рекомендуется шифровать базу данных

## Основано на

- [mtproto-proxy-installer](https://github.com/arblark/mtproto-proxy-installer) — оригинальный bash-скрипт
- [nineseconds/mtg](https://github.com/9seconds/mtg) — MTProto прокси
- [aiogram](https://github.com/aiogram/aiogram) — Telegram Bot Framework
- [paramiko](https://github.com/paramiko/paramiko) — SSH для Python
