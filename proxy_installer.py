from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from ssh_manager import SSHManager
from config import (
    DEFAULT_CONTAINER,
    DEFAULT_DNS,
    DEFAULT_DOMAIN,
    DEFAULT_IP_MODE,
    DEFAULT_PORT,
    INSTALL_TIMEOUT,
    MTPROTO_SETUP_URL,
)

logger = logging.getLogger(__name__)

SCRIPT_PATH = "/tmp/mtproto-setup.sh"
INSTALL_LOG = "/tmp/mtproto-install.log"
INSTALL_DONE = "/tmp/mtproto-install.done"

# Suppresses all interactive prompts from apt / dpkg / needrestart / ucf
_NONINTERACTIVE = (
    "DEBIAN_FRONTEND=noninteractive "
    "NEEDRESTART_MODE=a "
    "NEEDRESTART_SUSPEND=1 "
    "UCF_FORCE_CONFFOLD=1 "
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _parse_config(text: str) -> dict:
    result: dict = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _last_progress_line(log_text: str) -> str:
    """Extract the most recent meaningful status line from script output."""
    for raw_line in reversed(log_text.splitlines()):
        clean = _ANSI_RE.sub("", raw_line).strip()
        if not clean:
            continue
        for prefix in ("✓", "➜", "✗", "⚠"):
            if clean.startswith(prefix):
                return clean
    return ""


@dataclass
class ProxyConfig:
    port: int = DEFAULT_PORT
    domain: str = DEFAULT_DOMAIN
    dns: str = DEFAULT_DNS
    ip_mode: str = DEFAULT_IP_MODE
    container: str = DEFAULT_CONTAINER


@dataclass
class ProxyInfo:
    server_ip: str = ""
    port: int = 443
    secret: str = ""
    domain: str = ""
    dns: str = ""
    container: str = ""
    tme_link: str = ""
    tg_link: str = ""
    status: str = "unknown"
    error: str = ""


class ProxyInstaller:
    """Runs the official mtproto-setup.sh via --auto.

    Long-running commands are launched in the background on the remote server
    (nohup … &) and polled with lightweight SSH calls so the bot stays
    responsive and can update the Telegram message with live progress.
    """

    def __init__(self, ssh: SSHManager):
        self.ssh = ssh

    # ── internal helpers ────────────────────────────────────────

    async def _download_script(self) -> bool:
        r = await self.ssh.execute(
            f"curl -sSL {MTPROTO_SETUP_URL} -o {SCRIPT_PATH} && chmod +x {SCRIPT_PATH}",
            timeout=30,
        )
        if not r.ok:
            r = await self.ssh.execute(
                f"wget -qO {SCRIPT_PATH} {MTPROTO_SETUP_URL} && chmod +x {SCRIPT_PATH}",
                timeout=30,
            )
        return r.ok

    @staticmethod
    def _env_prefix(cfg: ProxyConfig, server_ip: str = "") -> str:
        parts = [
            f"MT_PORT={cfg.port}",
            f"MT_DOMAIN={cfg.domain}",
            f"MT_DNS={cfg.dns}",
            f"MT_IP_MODE={cfg.ip_mode}",
            f"MT_CONTAINER={cfg.container}",
        ]
        if server_ip:
            parts.insert(0, f"MT_SERVER_IP={server_ip}")
        return " ".join(parts)

    async def _read_remote_config(self) -> dict:
        r = await self.ssh.execute("cat /etc/mtproto-proxy/config 2>/dev/null")
        return _parse_config(r.stdout) if r.ok else {}

    async def _detect_ip(self) -> str:
        r = await self.ssh.execute(
            "curl -4 -s --max-time 5 https://ifconfig.me 2>/dev/null"
            " || curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null"
            " || hostname -I 2>/dev/null | awk '{print $1}'"
        )
        return r.stdout.strip().split("\n")[0].strip() if r.ok else ""

    def _fill_links(self, info: ProxyInfo) -> None:
        if info.server_ip and info.secret:
            base = f"server={info.server_ip}&port={info.port}&secret={info.secret}"
            info.tme_link = f"https://t.me/proxy?{base}"
            info.tg_link = f"tg://proxy?{base}"

    async def _run_script_background(self, args: str, env: str = "") -> None:
        """Launch script via nohup in background, logging to INSTALL_LOG."""
        await self.ssh.execute(f"rm -f {INSTALL_LOG} {INSTALL_DONE}")
        cmd = (
            f"nohup bash -c '"
            f"export {_NONINTERACTIVE}; "
            f"{env} "
            f"bash {SCRIPT_PATH} {args} > {INSTALL_LOG} 2>&1; "
            f"echo $? > {INSTALL_DONE}"
            f"' > /dev/null 2>&1 &"
        )
        await self.ssh.execute(cmd)

    async def _poll_until_done(self, timeout: int, progress_cb=None) -> tuple:
        """Poll INSTALL_DONE marker, calling progress_cb with latest log line.

        Returns (exit_code: int, log_text: str).
        """
        elapsed = 0
        interval = 5
        prev_line = ""

        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval

            r = await self.ssh.execute(f"cat {INSTALL_DONE} 2>/dev/null")
            done = r.ok and r.stdout.strip().isdigit()

            tail = await self.ssh.execute(f"tail -20 {INSTALL_LOG} 2>/dev/null")
            current_line = _last_progress_line(tail.stdout) if tail.ok else ""

            if current_line and current_line != prev_line and progress_cb:
                await progress_cb("script", current_line)
                prev_line = current_line

            if done:
                exit_code = int(r.stdout.strip())
                full = await self.ssh.execute(f"cat {INSTALL_LOG} 2>/dev/null")
                log_text = full.stdout if full.ok else ""
                await self.ssh.execute(f"rm -f {INSTALL_LOG} {INSTALL_DONE}")
                return exit_code, log_text

        await self.ssh.execute(
            f"kill $(pgrep -f '{SCRIPT_PATH}') 2>/dev/null || true"
        )
        full = await self.ssh.execute(f"cat {INSTALL_LOG} 2>/dev/null")
        log_text = full.stdout if full.ok else ""
        await self.ssh.execute(f"rm -f {INSTALL_LOG} {INSTALL_DONE}")
        return -1, log_text

    # ── public: read-only checks ────────────────────────────────

    async def check_server(self) -> dict:
        info: dict = {"os": "", "docker": False, "proxy_running": False, "ip": ""}

        r = await self.ssh.execute("cat /etc/os-release 2>/dev/null | head -2")
        if r.ok:
            for line in r.stdout.splitlines():
                if line.startswith("PRETTY_NAME="):
                    info["os"] = line.split("=", 1)[1].strip('"')
                    break

        r = await self.ssh.execute("docker --version 2>/dev/null")
        info["docker"] = r.ok

        r = await self.ssh.execute(
            "docker ps --format '{{.Names}}' 2>/dev/null | grep -w mtproto"
        )
        info["proxy_running"] = r.ok and "mtproto" in r.stdout
        info["ip"] = await self._detect_ip()
        return info

    async def get_status(self, container: str = DEFAULT_CONTAINER) -> ProxyInfo:
        result = ProxyInfo()
        cv = await self._read_remote_config()
        if cv:
            result.server_ip = cv.get("SERVER_IP", "")
            result.port = int(cv["EXT_PORT"]) if cv.get("EXT_PORT", "").isdigit() else 443
            result.secret = cv.get("SECRET", "")
            result.domain = cv.get("FAKE_DOMAIN", "")
            result.dns = cv.get("DNS_SERVER", "")
            result.container = cv.get("CONTAINER_NAME", container)

        r = await self.ssh.execute(
            f"docker ps --format '{{{{.Names}}}}' 2>/dev/null | grep -qw {container}"
        )
        result.status = "running" if r.ok else "stopped"
        self._fill_links(result)
        return result

    async def doctor(self, container: str = DEFAULT_CONTAINER) -> str:
        r = await self.ssh.execute(
            f"docker ps --format '{{{{.Names}}}}' 2>/dev/null | grep -qw {container}"
        )
        if not r.ok:
            return "Контейнер не запущен — диагностика недоступна"

        cv = await self._read_remote_config()
        dns = cv.get("DNS_SERVER", DEFAULT_DNS)
        ip_mode = cv.get("IP_PREFER", DEFAULT_IP_MODE)
        internal = cv.get("INTERNAL_PORT", "3128")
        secret = cv.get("SECRET", "")
        if not secret:
            return "Секрет не найден в конфигурации"

        r = await self.ssh.execute(
            f"docker exec {container} /mtg doctor --simple-run"
            f" -n {dns} -i {ip_mode} 0.0.0.0:{internal} {secret} 2>&1",
            timeout=30,
        )
        return r.stdout.strip() or r.stderr.strip() or "Нет вывода"

    async def get_logs(self, container: str = DEFAULT_CONTAINER, lines: int = 30) -> str:
        r = await self.ssh.execute(f"docker logs --tail {lines} {container} 2>&1")
        if r.ok:
            return r.stdout.strip()[-2000:] or "Логи пусты"
        return "Не удалось получить логи"

    # ── public: mutating operations (all via script) ────────────

    async def install(self, cfg: ProxyConfig, progress_cb=None) -> ProxyInfo:
        """Full install: download script → run --auto in background → poll."""
        result = ProxyInfo()

        async def _p(step: str, msg: str):
            if progress_cb:
                await progress_cb(step, msg)

        try:
            await _p("connect", "Подключение к серверу...")

            await _p("check", "Проверка сервера...")
            info = await self.check_server()
            result.server_ip = info["ip"]
            await _p("check", f"Сервер: {info.get('os', 'Linux')}, IP: {info['ip']}")

            await _p("download", "Скачивание скрипта установки...")
            if not await self._download_script():
                result.error = "Не удалось скачать mtproto-setup.sh"
                return result
            await _p("download", "Скрипт скачан")

            await _p("install", "Запуск установки...")

            env = self._env_prefix(cfg, server_ip=result.server_ip)
            await self._run_script_background("--auto", env=env)

            exit_code, log_text = await self._poll_until_done(
                timeout=INSTALL_TIMEOUT,
                progress_cb=_p,
            )

            if exit_code != 0:
                result.error = (
                    f"Скрипт завершился с ошибкой (код {exit_code}):\n"
                    f"{log_text[-800:]}"
                )
                return result

            await _p("config", "Чтение результатов...")
            cv = await self._read_remote_config()
            if cv:
                result.server_ip = cv.get("SERVER_IP", info["ip"])
                result.port = int(cv["EXT_PORT"]) if cv.get("EXT_PORT", "").isdigit() else cfg.port
                result.secret = cv.get("SECRET", "")
                result.domain = cv.get("FAKE_DOMAIN", cfg.domain)
                result.dns = cv.get("DNS_SERVER", cfg.dns)
                result.container = cv.get("CONTAINER_NAME", cfg.container)
            else:
                m = re.search(r"secret=([a-f0-9]+)", log_text)
                result.secret = m.group(1) if m else ""
                result.port = cfg.port
                result.domain = cfg.domain
                result.dns = cfg.dns
                result.container = cfg.container

            self._fill_links(result)
            result.status = "running"
            await _p("done", "Установка завершена!")

        except Exception as e:
            logger.exception("Installation failed")
            result.error = str(e)

        return result

    async def update(self, container: str = DEFAULT_CONTAINER) -> ProxyInfo:
        """Update via mtproto-setup.sh --update (background + poll)."""
        status = await self.get_status(container)
        if not status.secret:
            status.error = "Конфигурация не найдена на сервере"
            return status

        if not await self._download_script():
            status.error = "Не удалось скачать скрипт"
            return status

        await self._run_script_background("--update")
        exit_code, log_text = await self._poll_until_done(timeout=INSTALL_TIMEOUT)

        if exit_code != 0:
            status.error = f"Ошибка обновления:\n{log_text[-500:]}"
            return status

        updated = await self.get_status(container)
        updated.status = "running"
        return updated

    async def uninstall(self, container: str = DEFAULT_CONTAINER) -> str:
        """Uninstall: try script, then force-clean."""
        if await self._download_script():
            await self.ssh.execute(
                f"echo -e 'y\\ny\\n' | bash {SCRIPT_PATH} --uninstall 2>&1 || true",
                timeout=60,
            )

        await self.ssh.execute(f"docker rm -f {container} 2>/dev/null || true")
        await self.ssh.execute("docker rmi nineseconds/mtg 2>/dev/null || true")
        await self.ssh.execute("rm -rf /etc/mtproto-proxy")
        return "✓ Прокси полностью удалён"

    async def restart(self, container: str = DEFAULT_CONTAINER) -> bool:
        r = await self.ssh.execute(f"docker restart {container}")
        return r.ok
