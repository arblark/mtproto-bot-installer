# MTProto Proxy Telegram Bot

Telegram-бот для установки и управления MTProto прокси на ваших серверах — без консоли, в один клик.

## Возможности

- **Добавление серверов** — укажите IP, SSH-логин/пароль и бот запомнит
- **Два режима TLS:**
  - **Fake-TLS** — стандартный режим, прокси маскируется под HTTPS-трафик к указанному домену
  - **Real-TLS** — максимальная маскировка: реальный домен + Let's Encrypt сертификат + nginx. Трафик неотличим от настоящего HTTPS
- **Установка в один клик** — бот подключается по SSH и автоматически:
  - Устанавливает Docker
  - Скачивает и запускает [mtg](https://github.com/9seconds/mtg) прокси
  - Генерирует fake-TLS или real-TLS секрет
  - Настраивает nginx и Let's Encrypt (для Real-TLS)
  - Открывает порт в файрволе
  - Сохраняет конфигурацию
- **Готовые ссылки** — `t.me/proxy` и `tg://proxy` для подключения
- **Управление** — статус, диагностика (`--doctor`), логи, обновление, перезапуск, удаление прокси
- **Настройки** — порт, домен маскировки, DNS-сервер (Cloudflare, Google, Quad9, Яндекс, OpenDNS или свой)
- **Мульти-сервер** — управляйте несколькими серверами из одного бота
- **Шифрование** — SSH-пароли шифруются Fernet (AES) перед сохранением в БД
- **Админ-панель** — `/admin`, `/allusers`, `/allservers` для администраторов

---

## Пошаговая установка на Ubuntu VPS

### Что нужно заранее

| Что | Где взять |
|-----|-----------|
| VPS с Ubuntu 20.04+ | Любой хостер (Hetzner, DigitalOcean, Timeweb и т.д.) |
| Bot Token | Создать бота у [@BotFather](https://t.me/BotFather) в Telegram |
| Ваш Telegram ID | Узнать у [@userinfobot](https://t.me/userinfobot) |
| Домен (для Real-TLS) | A-запись должна указывать на IP сервера с прокси |

### Шаг 1. Подключитесь к серверу

```bash
ssh root@IP_ВАШЕГО_СЕРВЕРА
```

### Шаг 2. Установите Python и git

```bash
apt update && apt install -y python3 python3-pip python3-venv git
```

### Шаг 3. Скачайте бота

```bash
git clone https://github.com/arblark/mtproto-bot-installer.git /opt/mtproto-bot
cd /opt/mtproto-bot
```

### Шаг 4. Создайте виртуальное окружение и установите зависимости

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Шаг 5. Настройте конфигурацию

```bash
cp .env.example .env
nano .env
```

Заполните файл (замените значения на свои):

```
BOT_TOKEN=123456:ABC-DEF_ваш_токен_от_BotFather
ADMIN_IDS=123456789
```

Сохраните: `Ctrl+O` → `Enter` → `Ctrl+X`

> `ENCRYPT_KEY` генерируется автоматически при первом запуске.

### Шаг 6. Проверьте, что бот запускается

```bash
python main.py
```

Если видите в логах:
```
База данных инициализирована
Бот запущен
Start polling
```
— всё работает. Нажмите `Ctrl+C` для остановки.

### Шаг 7. Создайте systemd-сервис (автозапуск)

```bash
cat > /etc/systemd/system/mtproto-bot.service << 'EOF'
[Unit]
Description=MTProto Proxy Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mtproto-bot
ExecStart=/opt/mtproto-bot/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### Шаг 8. Запустите бот как сервис

```bash
systemctl daemon-reload
systemctl enable mtproto-bot
systemctl start mtproto-bot
```

### Шаг 9. Убедитесь, что всё работает

```bash
systemctl status mtproto-bot
```

Должно быть: `Active: active (running)`

---

## Быстрая установка (одна команда)

Замените `ТОКЕН` и `TELEGRAM_ID` на свои значения:

```bash
apt update && apt install -y python3 python3-pip python3-venv git \
  && git clone https://github.com/arblark/mtproto-bot-installer.git /opt/mtproto-bot \
  && cd /opt/mtproto-bot \
  && python3 -m venv venv \
  && source venv/bin/activate \
  && pip install -r requirements.txt \
  && cp .env.example .env \
  && sed -i 's|your_telegram_bot_token_here|ТОКЕН|' .env \
  && sed -i 's|123456789,987654321|TELEGRAM_ID|' .env \
  && cat > /etc/systemd/system/mtproto-bot.service << 'EOF'
[Unit]
Description=MTProto Proxy Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mtproto-bot
ExecStart=/opt/mtproto-bot/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable mtproto-bot && systemctl start mtproto-bot
```

---

## Как пользоваться ботом

1. Откройте бота в Telegram → `/start`
2. Нажмите **«Добавить сервер»**
3. Введите данные VPS: название, IP, SSH-порт, логин, пароль
4. Выберите **режим TLS**:
   - **Fake-TLS** — стандартный, укажите порт и домен маскировки
   - **Real-TLS** — укажите ваш реальный домен и email для Let's Encrypt
5. Выберите DNS-сервер
6. Нажмите **«Установить прокси»** — бот всё сделает автоматически
7. Получите готовую ссылку — отправьте друзьям или нажмите для подключения

### Fake-TLS vs Real-TLS

| | Fake-TLS | Real-TLS |
|---|----------|----------|
| Маскировка | Имитация HTTPS | Настоящий HTTPS (nginx + LE) |
| Домен | Любой (apple.com, etc.) | Свой реальный домен |
| Порт | Любой (рек. 443) | Только 443 |
| Нужен домен? | Нет | Да (A-запись → IP сервера) |
| Обнаружение | Может быть обнаружен DPI | Практически невозможно |
| Дополнительно | — | Anti-replay, domain fronting, blocklist |

> **Важно:** бот устанавливает прокси на *другие* серверы по SSH.
> Сервер, на котором работает бот, и сервер с прокси — это могут быть разные машины.

---

## Управление сервисом

| Действие | Команда |
|----------|---------|
| Статус | `systemctl status mtproto-bot` |
| Логи (последние 50 строк) | `journalctl -u mtproto-bot -n 50` |
| Логи в реальном времени | `journalctl -u mtproto-bot -f` |
| Перезапуск | `systemctl restart mtproto-bot` |
| Остановка | `systemctl stop mtproto-bot` |
| Обновление | см. ниже |

### Обновление бота

```bash
cd /opt/mtproto-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
systemctl restart mtproto-bot
```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/help` | Справка |
| `/servers` | Список серверов |
| `/admin` | Админ-панель (статистика) |
| `/allusers` | Все пользователи (админ) |
| `/allservers` | Все серверы (админ) |

---

## Структура проекта

```
mtproto-bot/
├── main.py              # Точка входа
├── bot.py               # Хендлеры Telegram-бота (FSM, callbacks)
├── keyboards.py         # Inline-клавиатуры
├── database.py          # SQLite база данных (с миграциями)
├── crypto.py            # Шифрование паролей (Fernet/AES)
├── ssh_manager.py       # SSH-подключение (paramiko)
├── proxy_installer.py   # Логика установки MTProto прокси
├── config.py            # Конфигурация из .env
├── requirements.txt     # Зависимости Python
├── .env.example         # Шаблон конфигурации
└── README.md
```

## Безопасность

- SSH-пароли шифруются AES (Fernet) перед сохранением в БД
- Ключ шифрования `ENCRYPT_KEY` генерируется автоматически и хранится в `.env`
- Сообщения с паролями автоматически удаляются из чата Telegram
- Рекомендуется использовать SSH-ключи вместо паролей

> **Не теряйте `.env` файл** — без `ENCRYPT_KEY` расшифровать пароли невозможно.

## Основано на

- [mtproto-proxy-installer](https://github.com/arblark/mtproto-proxy-installer) — оригинальный bash-скрипт (Fake-TLS + Real-TLS)
- [nineseconds/mtg](https://github.com/9seconds/mtg) — MTProto прокси
- [aiogram](https://github.com/aiogram/aiogram) — Telegram Bot Framework
- [paramiko](https://github.com/paramiko/paramiko) — SSH для Python
