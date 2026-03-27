import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

MTPROTO_SETUP_URL = (
    "https://raw.githubusercontent.com/arblark/mtproto-proxy-installer/main/mtproto-setup.sh"
)

DEFAULT_PORT = 443
DEFAULT_DOMAIN = "apple.com"
DEFAULT_DNS = "1.1.1.1"
DEFAULT_IP_MODE = "prefer-ipv4"
DEFAULT_CONTAINER = "mtproto"

DB_PATH = "bot_data.db"

SSH_TIMEOUT = 30
INSTALL_TIMEOUT = 300
