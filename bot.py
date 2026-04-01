from __future__ import annotations

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import Database
from ssh_manager import SSHManager
from proxy_installer import ProxyInstaller, ProxyConfig, ProxyInfo
from config import ADMIN_IDS, DEFAULT_PORT, DEFAULT_DOMAIN, DEFAULT_DNS
import keyboards as kb

logger = logging.getLogger(__name__)
router = Router()


class AddServer(StatesGroup):
    name = State()
    host = State()
    ssh_port = State()
    username = State()
    auth_type = State()
    credential = State()
    proxy_port = State()
    domain = State()
    dns = State()
    dns_custom = State()


class EditSetting(StatesGroup):
    waiting_value = State()


def get_db(state_data: dict | None = None) -> Database:
    """Retrieve DB instance from bot context — injected via middleware."""
    raise RuntimeError("DB should be injected via middleware")


# ──────────────────────────────────────────────────────────
# Middleware to inject DB
# ──────────────────────────────────────────────────────────

from aiogram import BaseMiddleware
from typing import Any, Awaitable, Callable, Dict


class DbMiddleware(BaseMiddleware):
    def __init__(self, db: Database):
        self.db = db

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        return await handler(event, data)


# ──────────────────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    user = message.from_user
    is_admin = user.id in ADMIN_IDS
    await db.upsert_user(user.id, user.username or "", user.first_name or "", is_admin)

    await message.answer(
        "🔐 <b>MTProto Proxy Manager</b>\n\n"
        "Установка и управление MTProto прокси для Telegram "
        "на ваших серверах — в один клик, без консоли.\n\n"
        "Выберите действие:",
        reply_markup=kb.main_menu(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Как пользоваться ботом</b>\n\n"
        "1️⃣ <b>Добавьте сервер</b> — укажите IP, SSH-логин и пароль вашего VPS\n"
        "2️⃣ <b>Установите прокси</b> — бот подключится по SSH и всё настроит автоматически\n"
        "3️⃣ <b>Получите ссылку</b> — готовая ссылка для подключения в Telegram\n\n"
        "🔧 <b>Что делает бот:</b>\n"
        "• Устанавливает Docker (если нет)\n"
        "• Скачивает и запускает mtg-прокси\n"
        "• Генерирует fake-TLS секрет\n"
        "• Открывает порт в файрволе\n"
        "• Выдаёт готовые ссылки t.me/proxy\n\n"
        "⚙️ <b>Команды:</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/servers — список серверов",
        parse_mode="HTML",
    )


@router.message(Command("servers"))
async def cmd_servers(message: Message, db: Database):
    servers = await db.get_servers(message.from_user.id)
    if not servers:
        await message.answer(
            "У вас пока нет серверов.\nНажмите «Добавить сервер» для начала.",
            reply_markup=kb.main_menu(),
        )
        return
    await message.answer("📋 <b>Ваши серверы:</b>", reply_markup=kb.server_list(servers), parse_mode="HTML")


# ──────────────────────────────────────────────────────────
# Callback: navigation
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "🔐 <b>MTProto Proxy Manager</b>\n\nВыберите действие:",
        reply_markup=kb.main_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "❌ Действие отменено.",
        reply_markup=kb.main_menu(),
    )


@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await call.message.edit_text(
        "📖 <b>Как пользоваться ботом</b>\n\n"
        "1️⃣ Добавьте сервер (IP + SSH-доступ)\n"
        "2️⃣ Нажмите «Установить прокси»\n"
        "3️⃣ Получите готовую ссылку для Telegram\n\n"
        "Бот подключается к вашему VPS по SSH, "
        "устанавливает Docker и mtg-прокси автоматически.",
        reply_markup=kb.main_menu(),
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
# Add server flow (FSM)
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "add_server")
async def cb_add_server(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddServer.name)
    await call.message.edit_text(
        "➕ <b>Добавление сервера</b>\n\n"
        "Введите название для сервера (например: «Мой VPS» или «Hetzner-1»):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AddServer.name)
async def fsm_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddServer.host)
    await message.answer(
        "🌐 Введите <b>IP-адрес</b> или <b>домен</b> сервера:\n"
        "<i>Например: 203.0.113.1</i>",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AddServer.host)
async def fsm_host(message: Message, state: FSMContext):
    host = message.text.strip()
    await state.update_data(host=host)
    await state.set_state(AddServer.ssh_port)
    await message.answer(
        "🔌 Введите <b>SSH-порт</b> (по умолчанию 22):\n"
        "<i>Просто нажмите отправить для порта 22</i>",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AddServer.ssh_port)
async def fsm_ssh_port(message: Message, state: FSMContext):
    text = message.text.strip()
    port = 22
    if text and text.isdigit():
        port = int(text)
    await state.update_data(ssh_port=port)
    await state.set_state(AddServer.username)
    await message.answer(
        "👤 Введите <b>имя пользователя</b> SSH (по умолчанию root):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AddServer.username)
async def fsm_username(message: Message, state: FSMContext):
    username = message.text.strip() or "root"
    await state.update_data(username=username)
    await state.set_state(AddServer.auth_type)

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    await message.answer(
        "🔑 Выберите <b>способ авторизации</b>:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Пароль", callback_data="auth_password")],
            [InlineKeyboardButton(text="🔑 SSH-ключ", callback_data="auth_key")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_({"auth_password", "auth_key"}), AddServer.auth_type)
async def fsm_auth_type(call: CallbackQuery, state: FSMContext):
    auth_type = "password" if call.data == "auth_password" else "key"
    await state.update_data(auth_type=auth_type)
    await state.set_state(AddServer.credential)

    if auth_type == "password":
        await call.message.edit_text(
            "🔒 Введите <b>пароль</b> SSH:\n\n"
            "<i>⚠️ Сообщение с паролем будет удалено после сохранения</i>",
            reply_markup=kb.cancel_kb(),
            parse_mode="HTML",
        )
    else:
        await call.message.edit_text(
            "🔑 Отправьте <b>приватный SSH-ключ</b> текстом:\n\n"
            "<i>Начинается с -----BEGIN ... PRIVATE KEY-----\n"
            "⚠️ Сообщение с ключом будет удалено после сохранения</i>",
            reply_markup=kb.cancel_kb(),
            parse_mode="HTML",
        )


@router.message(AddServer.credential)
async def fsm_credential(message: Message, state: FSMContext):
    credential = message.text.strip()
    await state.update_data(credential=credential)

    try:
        await message.delete()
    except Exception:
        pass

    await state.set_state(AddServer.proxy_port)
    await message.answer(
        f"🔌 Введите <b>порт прокси</b> (по умолчанию {DEFAULT_PORT}):\n"
        f"<i>443 — лучший выбор для обхода блокировок</i>",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(AddServer.proxy_port)
async def fsm_proxy_port(message: Message, state: FSMContext):
    text = message.text.strip()
    port = DEFAULT_PORT
    if text and text.isdigit():
        port = int(text)
    await state.update_data(proxy_port=port)
    await state.set_state(AddServer.domain)
    await message.answer(
        f"🌐 Введите <b>домен маскировки</b> (по умолчанию {DEFAULT_DOMAIN}):\n"
        f"<i>Трафик будет выглядеть как HTTPS к этому домену</i>",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


DNS_INFO = {
    "1.1.1.1": "Cloudflare — быстрый, приватный, без цензуры",
    "8.8.8.8": "Google — надёжный, глобальная сеть, высокий аптайм",
    "9.9.9.9": "Quad9 — блокирует вредоносные домены, приватный",
    "77.88.8.8": "Яндекс — быстрый в РФ/СНГ, фильтрация мошенников",
    "208.67.222.222": "OpenDNS (Cisco) — гибкая фильтрация, надёжный",
}


@router.message(AddServer.domain)
async def fsm_domain(message: Message, state: FSMContext):
    domain = message.text.strip() or DEFAULT_DOMAIN
    await state.update_data(domain=domain)
    await state.set_state(AddServer.dns)

    lines = ["📡 <b>Выберите DNS-сервер:</b>\n"]
    for ip, desc in DNS_INFO.items():
        lines.append(f"<code>{ip}</code> — {desc}")
    lines.append("\n<i>DNS влияет на скорость резолва доменов внутри прокси.\n"
                 "Cloudflare (1.1.1.1) — лучший выбор для большинства.</i>")

    await message.answer(
        "\n".join(lines),
        reply_markup=kb.dns_selector(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dns:"), AddServer.dns)
async def fsm_dns_select(call: CallbackQuery, state: FSMContext, db: Database):
    value = call.data.split(":", 1)[1]

    if value == "custom":
        await state.set_state(AddServer.dns_custom)
        await call.message.edit_text(
            "📡 Введите <b>IP-адрес DNS-сервера</b>:\n"
            "<i>Например: 1.0.0.1</i>",
            reply_markup=kb.cancel_kb(),
            parse_mode="HTML",
        )
        return

    await _save_server(call.message, state, db, call.from_user.id, value)


@router.message(AddServer.dns_custom)
async def fsm_dns_custom(message: Message, state: FSMContext, db: Database):
    dns = message.text.strip()
    if not dns:
        dns = DEFAULT_DNS
    await _save_server(message, state, db, message.from_user.id, dns)


async def _save_server(msg, state: FSMContext, db: Database, user_id: int, dns: str):
    data = await state.get_data()
    await state.clear()

    server_id = await db.add_server(
        user_id=user_id,
        name=data["name"],
        host=data["host"],
        ssh_port=data["ssh_port"],
        username=data["username"],
        auth_type=data["auth_type"],
        credential=data["credential"],
        proxy_port=data["proxy_port"],
        domain=data["domain"],
        dns=dns,
    )

    dns_label = DNS_INFO.get(dns, dns)
    text = (
        f"✅ <b>Сервер добавлен!</b>\n\n"
        f"📛 {data['name']}\n"
        f"🌐 {data['host']}:{data['ssh_port']}\n"
        f"👤 {data['username']}\n"
        f"🔌 Порт прокси: {data['proxy_port']}\n"
        f"🌍 Домен: {data['domain']}\n"
        f"📡 DNS: {dns} ({dns_label})\n\n"
        f"Нажмите «Установить прокси» для запуска установки."
    )

    if hasattr(msg, "edit_text"):
        await msg.edit_text(text, reply_markup=kb.server_actions(server_id, "new"), parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb.server_actions(server_id, "new"), parse_mode="HTML")


# ──────────────────────────────────────────────────────────
# Server list & details
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_servers")
async def cb_my_servers(call: CallbackQuery, db: Database):
    servers = await db.get_servers(call.from_user.id)
    if not servers:
        await call.message.edit_text(
            "У вас пока нет серверов.",
            reply_markup=kb.main_menu(),
        )
        return
    await call.message.edit_text(
        "📋 <b>Ваши серверы:</b>",
        reply_markup=kb.server_list(servers),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("server:"))
async def cb_server_detail(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    status_text = {"new": "⚪ Новый", "installed": "🟢 Работает", "error": "🔴 Ошибка"}.get(
        server["status"], server["status"]
    )

    text = (
        f"📛 <b>{server['name'] or server['host']}</b>\n\n"
        f"🌐 Хост: <code>{server['host']}</code>\n"
        f"🔌 SSH: {server['ssh_port']} | Прокси: {server['proxy_port']}\n"
        f"👤 {server['username']}\n"
        f"🌍 Домен: {server['domain']}\n"
        f"📡 DNS: {server['dns']}\n"
        f"📊 Статус: {status_text}\n"
    )

    if server["tme_link"]:
        text += f"\n🔗 <a href=\"{server['tme_link']}\">Подключиться к прокси</a>\n"

    await call.message.edit_text(
        text,
        reply_markup=kb.server_actions(server_id, server["status"]),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ──────────────────────────────────────────────────────────
# Install proxy
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("install:"))
async def cb_install(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    status_msg = await call.message.edit_text(
        "🚀 <b>Установка MTProto Proxy</b>\n\n"
        "⏳ Подключение к серверу...",
        parse_mode="HTML",
    )

    steps_done = []

    async def progress_cb(step: str, msg: str):
        steps_done.append(f"{'✅' if step != 'done' else '🎉'} {msg}")
        text = "🚀 <b>Установка MTProto Proxy</b>\n\n" + "\n".join(steps_done)
        try:
            await bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML",
            )
        except Exception:
            pass

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )

        async with ssh:
            installer = ProxyInstaller(ssh)
            cfg = ProxyConfig(
                port=server["proxy_port"],
                domain=server["domain"],
                dns=server["dns"],
            )
            result = await installer.install(cfg, progress_cb=progress_cb)

        if result.error:
            await db.update_server(server_id, status="error")
            await bot.edit_message_text(
                f"❌ <b>Ошибка установки</b>\n\n{result.error}",
                chat_id=call.message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=kb.server_actions(server_id, "error"),
                parse_mode="HTML",
            )
            return

        await db.update_server(
            server_id,
            status="installed",
            secret=result.secret,
            server_ip=result.server_ip,
            tme_link=result.tme_link,
        )

        await bot.edit_message_text(
            f"🎉 <b>Прокси установлен!</b>\n\n"
            f"🌐 Сервер: <code>{result.server_ip}</code>\n"
            f"🔌 Порт: <code>{result.port}</code>\n"
            f"🔑 Секрет: <code>{result.secret}</code>\n"
            f"🌍 Домен: {result.domain}\n\n"
            f"📱 <b>Ссылка для подключения:</b>\n"
            f"<a href=\"{result.tme_link}\">👉 Подключиться к прокси</a>\n\n"
            f"<code>{result.tme_link}</code>",
            chat_id=call.message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=kb.server_actions(server_id, "installed"),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:
        logger.exception("Install failed")
        await db.update_server(server_id, status="error")
        error_text = str(e)
        if "Authentication failed" in error_text:
            error_text = "Ошибка авторизации SSH. Проверьте логин/пароль."
        elif "timed out" in error_text:
            error_text = "Таймаут подключения. Проверьте IP и доступность сервера."
        elif "No route to host" in error_text or "Connection refused" in error_text:
            error_text = "Сервер недоступен. Проверьте IP и SSH-порт."

        await bot.edit_message_text(
            f"❌ <b>Ошибка</b>\n\n{error_text}",
            chat_id=call.message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=kb.server_actions(server_id, "error"),
            parse_mode="HTML",
        )


# ──────────────────────────────────────────────────────────
# Status / Links
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("status:"))
async def cb_status(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("⏳ Проверка статуса...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            info = await installer.get_status()

        status_icon = "🟢" if info.status == "running" else "🔴"
        status_text = "Работает" if info.status == "running" else "Остановлен"

        await bot.edit_message_text(
            f"📊 <b>Статус прокси</b>\n\n"
            f"{status_icon} {status_text}\n"
            f"🌐 IP: <code>{info.server_ip}</code>\n"
            f"🔌 Порт: <code>{info.port}</code>\n"
            f"🌍 Домен: {info.domain}\n"
            f"📡 DNS: {info.dns}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )
    except Exception as e:
        await bot.edit_message_text(
            f"❌ Не удалось проверить статус:\n{e}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("links:"))
async def cb_links(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    if not server["tme_link"]:
        await call.answer("Ссылки ещё не сгенерированы. Установите прокси.", show_alert=True)
        return

    tg_link = server["tme_link"].replace("https://t.me/proxy", "tg://proxy")

    await call.message.edit_text(
        f"🔗 <b>Ссылки для подключения</b>\n\n"
        f"📱 <a href=\"{server['tme_link']}\">👉 Подключиться (t.me)</a>\n\n"
        f"<code>{server['tme_link']}</code>\n\n"
        f"<code>{tg_link}</code>\n\n"
        f"<i>Нажмите на ссылку или скопируйте и отправьте друзьям</i>",
        reply_markup=kb.back_to_server(server_id),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ──────────────────────────────────────────────────────────
# Doctor / Logs / Test SSH
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("doctor:"))
async def cb_doctor(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("🩺 Запуск диагностики...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            report = await installer.doctor()

        await bot.edit_message_text(
            f"🩺 <b>Диагностика mtg</b>\n\n<pre>{report[:3500]}</pre>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.back_to_server(server_id),
            parse_mode="HTML",
        )
    except Exception as e:
        await bot.edit_message_text(
            f"❌ Ошибка диагностики:\n{e}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("logs:"))
async def cb_logs(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("📜 Получение логов...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            logs = await installer.get_logs()

        await bot.edit_message_text(
            f"📜 <b>Логи контейнера</b>\n\n<pre>{logs[:3500]}</pre>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.back_to_server(server_id),
            parse_mode="HTML",
        )
    except Exception as e:
        await bot.edit_message_text(
            f"❌ Ошибка:\n{e}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("test_ssh:"))
async def cb_test_ssh(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("🔌 Проверка SSH-подключения...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            info = await installer.check_server()

        await bot.edit_message_text(
            f"✅ <b>SSH-подключение успешно!</b>\n\n"
            f"🖥 ОС: {info.get('os', 'н/д')}\n"
            f"🌐 IP: <code>{info.get('ip', 'н/д')}</code>\n"
            f"🐳 Docker: {'установлен' if info.get('docker') else 'не установлен'}\n"
            f"📡 Прокси: {'работает' if info.get('proxy_running') else 'не запущен'}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )
    except Exception as e:
        error_text = str(e)
        if "Authentication failed" in error_text:
            error_text = "Ошибка авторизации. Проверьте логин/пароль."
        elif "timed out" in error_text:
            error_text = "Таймаут подключения. Проверьте IP и доступность."
        elif "No route to host" in error_text or "Connection refused" in error_text:
            error_text = "Сервер недоступен. Проверьте IP и SSH-порт."

        await bot.edit_message_text(
            f"❌ <b>SSH-подключение не удалось</b>\n\n{error_text}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


# ──────────────────────────────────────────────────────────
# Update / Restart / Uninstall
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("update:"))
async def cb_update(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("🔄 Обновление прокси...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            result = await installer.update()

        if result.error:
            await bot.edit_message_text(
                f"❌ Ошибка обновления:\n{result.error}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=kb.server_actions(server_id, server["status"]),
                parse_mode="HTML",
            )
        else:
            await bot.edit_message_text(
                "✅ <b>Прокси обновлён!</b>\n\nОбраз обновлён, контейнер перезапущен.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=kb.server_actions(server_id, "installed"),
                parse_mode="HTML",
            )
    except Exception as e:
        await bot.edit_message_text(
            f"❌ Ошибка: {e}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("restart:"))
async def cb_restart(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("🔃 Перезапуск прокси...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            ok = await installer.restart()

        if ok:
            await bot.edit_message_text(
                "✅ Прокси перезапущен!",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=kb.server_actions(server_id, "installed"),
                parse_mode="HTML",
            )
        else:
            await bot.edit_message_text(
                "❌ Не удалось перезапустить контейнер.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=kb.server_actions(server_id, server["status"]),
                parse_mode="HTML",
            )
    except Exception as e:
        await bot.edit_message_text(
            f"❌ Ошибка: {e}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("uninstall:"))
async def cb_uninstall_confirm(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    await call.message.edit_text(
        "⚠️ <b>Удалить прокси с сервера?</b>\n\n"
        "Будут удалены: контейнер, образ, конфигурация.\n"
        "Сервер останется в списке бота.",
        reply_markup=kb.confirm_action("uninstall", server_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("confirm_uninstall:"))
async def cb_uninstall_do(call: CallbackQuery, db: Database, bot: Bot):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text("🗑 Удаление прокси...", parse_mode="HTML")

    try:
        ssh = SSHManager(
            host=server["host"],
            port=server["ssh_port"],
            username=server["username"],
            password=server["credential"] if server["auth_type"] == "password" else None,
            key=server["credential"] if server["auth_type"] == "key" else None,
        )
        async with ssh:
            installer = ProxyInstaller(ssh)
            report = await installer.uninstall()

        await db.update_server(server_id, status="new", secret="", server_ip="", tme_link="")

        await bot.edit_message_text(
            f"🗑 <b>Прокси удалён</b>\n\n{report}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, "new"),
            parse_mode="HTML",
        )
    except Exception as e:
        await bot.edit_message_text(
            f"❌ Ошибка: {e}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=kb.server_actions(server_id, server["status"]),
            parse_mode="HTML",
        )


# ──────────────────────────────────────────────────────────
# Delete server from bot
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("delete:"))
async def cb_delete_confirm(call: CallbackQuery):
    server_id = int(call.data.split(":")[1])
    await call.message.edit_text(
        "⚠️ <b>Удалить сервер из бота?</b>\n\n"
        "Прокси на сервере НЕ будет удалён — только запись в боте.",
        reply_markup=kb.confirm_action("delete", server_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_delete_do(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    await db.delete_server(server_id, call.from_user.id)
    await call.message.edit_text(
        "✅ Сервер удалён из бота.",
        reply_markup=kb.main_menu(),
    )


# ──────────────────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("settings:"))
async def cb_settings(call: CallbackQuery, db: Database):
    server_id = int(call.data.split(":")[1])
    server = await db.get_server(server_id, call.from_user.id)
    if not server:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"⚙️ <b>Настройки сервера</b>\n\n"
        f"🔌 Порт: {server['proxy_port']}\n"
        f"🌍 Домен: {server['domain']}\n"
        f"📡 DNS: {server['dns']}\n\n"
        f"<i>Изменения вступят в силу при переустановке прокси</i>",
        reply_markup=kb.settings_menu(server_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_port:"))
async def cb_set_port(call: CallbackQuery, state: FSMContext):
    server_id = int(call.data.split(":")[1])
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(setting="proxy_port", server_id=server_id)
    await call.message.edit_text(
        "🔌 Введите новый <b>порт прокси</b> (1-65535):",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_domain:"))
async def cb_set_domain(call: CallbackQuery, state: FSMContext):
    server_id = int(call.data.split(":")[1])
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(setting="domain", server_id=server_id)
    await call.message.edit_text(
        "🌍 Введите новый <b>домен маскировки</b>:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_dns:"))
async def cb_set_dns(call: CallbackQuery, state: FSMContext):
    server_id = int(call.data.split(":")[1])
    await state.set_state(EditSetting.waiting_value)
    await state.update_data(setting="dns", server_id=server_id)
    await call.message.edit_text(
        "📡 Введите новый <b>DNS сервер</b>:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML",
    )


@router.message(EditSetting.waiting_value)
async def fsm_edit_setting(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    await state.clear()

    setting = data["setting"]
    server_id = data["server_id"]
    value = message.text.strip()

    if setting == "proxy_port":
        if not value.isdigit() or not (1 <= int(value) <= 65535):
            await message.answer("❌ Некорректный порт. Попробуйте снова.")
            return
        await db.update_server(server_id, proxy_port=int(value))
    elif setting == "domain":
        await db.update_server(server_id, domain=value)
    elif setting == "dns":
        await db.update_server(server_id, dns=value)

    server = await db.get_server(server_id, message.from_user.id)
    await message.answer(
        f"✅ Настройка обновлена!\n\n"
        f"<i>Для применения переустановите прокси.</i>",
        reply_markup=kb.server_actions(server_id, server["status"] if server else "new"),
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
# Admin panel
# ──────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, db: Database):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return

    stats = await db.get_stats()
    by_status = stats.get("by_status", {})

    installed = by_status.get("installed", 0)
    new = by_status.get("new", 0)
    error = by_status.get("error", 0)

    await message.answer(
        f"👑 <b>Админ-панель</b>\n\n"
        f"👤 Пользователей: <b>{stats['users']}</b>\n"
        f"👤 С серверами: <b>{stats['users_with_servers']}</b>\n\n"
        f"🖥 Серверов всего: <b>{stats['servers']}</b>\n"
        f"🟢 Установлено: <b>{installed}</b>\n"
        f"⚪ Новых: <b>{new}</b>\n"
        f"🔴 С ошибкой: <b>{error}</b>\n\n"
        f"<b>Команды:</b>\n"
        f"/admin — эта панель\n"
        f"/allusers — все пользователи\n"
        f"/allservers — все серверы",
        parse_mode="HTML",
    )


@router.message(Command("allusers"))
async def cmd_all_users(message: Message, db: Database):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return

    users = await db.get_all_users()
    if not users:
        await message.answer("Пользователей пока нет.")
        return

    lines = ["👤 <b>Все пользователи:</b>\n"]
    for u in users[:50]:
        name = u["first_name"] or u["username"] or str(u["user_id"])
        admin_mark = " 👑" if u["is_admin"] else ""
        lines.append(f"• <code>{u['user_id']}</code> — {name}{admin_mark}")

    if len(users) > 50:
        lines.append(f"\n<i>... и ещё {len(users) - 50}</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("allservers"))
async def cmd_all_servers(message: Message, db: Database):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return

    servers = await db.get_all_servers()
    if not servers:
        await message.answer("Серверов пока нет.")
        return

    lines = ["🖥 <b>Все серверы:</b>\n"]
    for s in servers[:30]:
        status_icon = {"installed": "🟢", "error": "🔴", "new": "⚪"}.get(s["status"], "❓")
        owner = s.get("tg_username") or str(s["user_id"])
        lines.append(
            f"{status_icon} <code>{s['host']}</code> "
            f":{s['proxy_port']} — @{owner} ({s['name'] or '—'})"
        )

    if len(servers) > 30:
        lines.append(f"\n<i>... и ещё {len(servers) - 30}</i>")

    await message.answer("\n".join(lines), parse_mode="HTML")
