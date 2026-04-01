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


def _parse_config(text: str) -> dict:
    """Parse /etc/mtproto-proxy/config key=value file."""
    result: dict = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


class ProxyInstaller:
    """Installs MTProto proxy by downloading and running the official
    mtproto-setup.sh script with --auto and environment variables."""

    def __init__(self, ssh: SSHManager):
        self.ssh = ssh

    # ── helpers ──────────────────────────────────────────────────

    async def _download_script(self) -> bool:
        """Download mtproto-setup.sh to /tmp on the remote server."""
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

    def _build_env(self, cfg: ProxyConfig, server_ip: str = "") -> str:
        """Build environment variable prefix for --auto mode."""
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
        if r.ok:
            return _parse_config(r.stdout)
        return {}

    async def _detect_ip(self) -> str:
        r = await self.ssh.execute(
            "curl -4 -s --max-time 5 https://ifconfig.me 2>/dev/null"
            " || curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null"
            " || hostname -I 2>/dev/null | awk '{print $1}'"
        )
        if r.ok:
            return r.stdout.strip().split("\n")[0].strip()
        return ""

    # ── public API ──────────────────────────────────────────────

    async def check_server(self) -> dict:
        """Quick server health check: OS, Docker, existing proxy."""
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

    async def install(self, cfg: ProxyConfig, progress_cb=None) -> ProxyInfo:
        """Download mtproto-setup.sh → run with --auto and env vars."""
        result = ProxyInfo()

        async def _progress(step: str, msg: str):
            if progress_cb:
                await progress_cb(step, msg)

        try:
            await _progress("connect", "Подключение к серверу...")

            await _progress("check", "Проверка сервера...")
            info = await self.check_server()
            result.server_ip = info["ip"]
            os_name = info.get("os", "Linux")
            await _progress("check", f"Сервер: {os_name}, IP: {info['ip']}")

            await _progress("download", "Скачивание скрипта установки...")
            if not await self._download_script():
                result.error = "Не удалось скачать mtproto-setup.sh"
                return result
            await _progress("download", "Скрипт скачан")

            await _progress("install", "Запуск установки (--auto)...")
            env_prefix = self._build_env(cfg, server_ip=result.server_ip)

            last_status = {"text": ""}
            loop = asyncio.get_event_loop()

            def _on_line(line: str):
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                if not clean:
                    return
                if clean.startswith("✓") or clean.startswith("➜") or clean.startswith("✗"):
                    last_status["text"] = clean

            r = await self.ssh.execute_stream(
                f"{env_prefix} bash {SCRIPT_PATH} --auto 2>&1",
                timeout=INSTALL_TIMEOUT,
                on_output=_on_line,
            )

            if last_status["text"]:
                await _progress("install", last_status["text"])

            output = r.stdout + "\n" + r.stderr
            if not r.ok:
                result.error = (
                    f"Скрипт завершился с ошибкой (код {r.exit_code}):\n"
                    f"{output[-800:]}"
                )
                return result

            await _progress("install", "Скрипт выполнен успешно")

            await _progress("config", "Чтение конфигурации...")
            cv = await self._read_remote_config()
            if cv:
                result.server_ip = cv.get("SERVER_IP", info["ip"])
                result.port = (
                    int(cv["EXT_PORT"])
                    if cv.get("EXT_PORT", "").isdigit()
                    else cfg.port
                )
                result.secret = cv.get("SECRET", "")
                result.domain = cv.get("FAKE_DOMAIN", cfg.domain)
                result.dns = cv.get("DNS_SERVER", cfg.dns)
                result.container = cv.get("CONTAINER_NAME", cfg.container)
            else:
                secret_match = re.search(r"secret=([a-f0-9]+)", output)
                if secret_match:
                    result.secret = secret_match.group(1)
                result.port = cfg.port
                result.domain = cfg.domain
                result.dns = cfg.dns
                result.container = cfg.container

            if result.server_ip and result.secret:
                ip = result.server_ip
                result.tme_link = (
                    f"https://t.me/proxy?server={ip}"
                    f"&port={result.port}&secret={result.secret}"
                )
                result.tg_link = (
                    f"tg://proxy?server={ip}"
                    f"&port={result.port}&secret={result.secret}"
                )

            result.status = "running"
            await _progress("done", "Установка завершена!")

        except Exception as e:
            logger.exception("Installation failed")
            result.error = str(e)

        return result

    async def get_status(self, container: str = DEFAULT_CONTAINER) -> ProxyInfo:
        """Read /etc/mtproto-proxy/config and docker status."""
        result = ProxyInfo()

        cv = await self._read_remote_config()
        if cv:
            result.server_ip = cv.get("SERVER_IP", "")
            result.port = (
                int(cv["EXT_PORT"])
                if cv.get("EXT_PORT", "").isdigit()
                else 443
            )
            result.secret = cv.get("SECRET", "")
            result.domain = cv.get("FAKE_DOMAIN", "")
            result.dns = cv.get("DNS_SERVER", "")
            result.container = cv.get("CONTAINER_NAME", container)

        r = await self.ssh.execute(
            f"docker ps --format '{{{{.Names}}}}' 2>/dev/null | grep -qw {container}"
        )
        result.status = "running" if r.ok else "stopped"

        if result.server_ip and result.secret:
            result.tme_link = (
                f"https://t.me/proxy?server={result.server_ip}"
                f"&port={result.port}&secret={result.secret}"
            )
            result.tg_link = (
                f"tg://proxy?server={result.server_ip}"
                f"&port={result.port}&secret={result.secret}"
            )

        return result

    async def uninstall(self, container: str = DEFAULT_CONTAINER) -> str:
        """Download script and run --uninstall (auto-answer 'yes' to prompts)."""
        if await self._download_script():
            r = await self.ssh.execute(
                f"echo -e 'y\\ny\\n' | bash {SCRIPT_PATH} --uninstall 2>&1",
                timeout=60,
            )
            return "✓ Прокси удалён через скрипт"

        messages = []
        r = await self.ssh.execute(f"docker rm -f {container} 2>/dev/null")
        messages.append("Контейнер удалён" if r.ok else "Контейнер не найден")

        r = await self.ssh.execute(
            "cat /etc/mtproto-proxy/config 2>/dev/null | grep EXT_PORT"
        )
        if r.ok:
            port = r.stdout.strip().split("=")[-1].strip()
            if port.isdigit():
                await self.ssh.execute(
                    f"command -v ufw &>/dev/null && ufw delete allow {port}/tcp 2>/dev/null;"
                    f" command -v firewall-cmd &>/dev/null"
                    f" && firewall-cmd --permanent --remove-port={port}/tcp 2>/dev/null"
                    f" && firewall-cmd --reload 2>/dev/null; true"
                )
                messages.append(f"Порт {port} закрыт в файрволе")

        await self.ssh.execute("rm -rf /etc/mtproto-proxy")
        messages.append("Конфигурация удалена")

        return "\n".join(f"✓ {m}" for m in messages)

    async def restart(self, container: str = DEFAULT_CONTAINER) -> bool:
        r = await self.ssh.execute(f"docker restart {container}")
        return r.ok

    async def update(self, container: str = DEFAULT_CONTAINER) -> ProxyInfo:
        """Download script and run --update."""
        status = await self.get_status(container)
        if not status.secret:
            status.error = "Конфигурация не найдена на сервере"
            return status

        if not await self._download_script():
            status.error = "Не удалось скачать скрипт для обновления"
            return status

        r = await self.ssh.execute(
            f"bash {SCRIPT_PATH} --update 2>&1",
            timeout=INSTALL_TIMEOUT,
        )
        if not r.ok:
            status.error = f"Ошибка обновления:\n{(r.stdout + r.stderr)[-500:]}"
            return status

        updated = await self.get_status(container)
        updated.status = "running"
        return updated

    async def doctor(self, container: str = DEFAULT_CONTAINER) -> str:
        """Run mtg doctor directly (not in the script — no --doctor flag)."""
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
        """Get last N lines of container logs."""
        r = await self.ssh.execute(f"docker logs --tail {lines} {container} 2>&1")
        if r.ok:
            return r.stdout.strip()[-2000:] or "Логи пусты"
        return "Не удалось получить логи"
