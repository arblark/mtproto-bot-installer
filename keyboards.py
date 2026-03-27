from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить сервер", callback_data="add_server")],
        [InlineKeyboardButton(text="📋 Мои серверы", callback_data="my_servers")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])


def server_list(servers: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in servers:
        status_icon = "🟢" if s["status"] == "installed" else "🔴" if s["status"] == "error" else "⚪"
        label = s["name"] or s["host"]
        buttons.append([
            InlineKeyboardButton(text=f"{status_icon} {label}", callback_data=f"server:{s['id']}")
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def server_actions(server_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "new":
        buttons.append([
            InlineKeyboardButton(text="🚀 Установить прокси", callback_data=f"install:{server_id}")
        ])
    elif status == "installed":
        buttons.append([
            InlineKeyboardButton(text="📊 Статус", callback_data=f"status:{server_id}"),
            InlineKeyboardButton(text="🔗 Ссылки", callback_data=f"links:{server_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"update:{server_id}"),
            InlineKeyboardButton(text="🔃 Перезапуск", callback_data=f"restart:{server_id}"),
        ])
        buttons.append([
            InlineKeyboardButton(text="🗑 Удалить прокси", callback_data=f"uninstall:{server_id}"),
        ])
    elif status == "error":
        buttons.append([
            InlineKeyboardButton(text="🔁 Повторить установку", callback_data=f"install:{server_id}")
        ])

    buttons.append([
        InlineKeyboardButton(text="✏️ Настройки", callback_data=f"settings:{server_id}"),
        InlineKeyboardButton(text="❌ Удалить сервер", callback_data=f"delete:{server_id}"),
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ К серверам", callback_data="my_servers")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_action(action: str, server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}:{server_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"server:{server_id}"),
        ]
    ])


def settings_menu(server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔌 Порт прокси", callback_data=f"set_port:{server_id}")],
        [InlineKeyboardButton(text="🌐 Домен маскировки", callback_data=f"set_domain:{server_id}")],
        [InlineKeyboardButton(text="📡 DNS сервер", callback_data=f"set_dns:{server_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"server:{server_id}")],
    ])


def back_to_server(server_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"server:{server_id}")]
    ])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
