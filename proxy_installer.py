import logging
import re
from dataclasses import dataclass, field

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
    """Orchestrates MTProto proxy installation via SSH."""

    def __init__(self, ssh: SSHManager):
        self.ssh = ssh

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

        r = await self.ssh.execute("docker ps --format '{{.Names}}' 2>/dev/null | grep -w mtproto")
        info["proxy_running"] = r.ok and "mtproto" in r.stdout

        r = await self.ssh.execute(
            "curl -4 -s --max-time 5 https://ifconfig.me 2>/dev/null"
            " || curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null"
            " || hostname -I 2>/dev/null | awk '{print $1}'"
        )
        if r.ok:
            info["ip"] = r.stdout.strip().split("\n")[0].strip()

        return info

    async def install(self, cfg: ProxyConfig, progress_cb=None) -> ProxyInfo:
        """Full installation flow. progress_cb(step, message) for live updates."""
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

            if not info["docker"]:
                await _progress("docker", "Установка Docker...")
                r = await self.ssh.execute(
                    "if command -v apt-get &>/dev/null; then"
                    "  apt-get update -qq && apt-get install -y -qq docker.io;"
                    " elif command -v yum &>/dev/null; then"
                    "  yum install -y docker && systemctl start docker;"
                    " elif command -v dnf &>/dev/null; then"
                    "  dnf install -y docker && systemctl start docker;"
                    " else"
                    "  curl -fsSL https://get.docker.com | sh;"
                    " fi"
                    " && systemctl enable docker && systemctl start docker",
                    timeout=INSTALL_TIMEOUT,
                )
                if not r.ok:
                    result.error = f"Не удалось установить Docker:\n{r.stderr[:500]}"
                    return result
                await _progress("docker", "Docker установлен")
            else:
                await _progress("docker", "Docker уже установлен")

            await _progress("pull", "Скачивание образа mtg...")
            r = await self.ssh.execute("docker pull nineseconds/mtg", timeout=INSTALL_TIMEOUT)
            if not r.ok:
                result.error = f"Не удалось скачать образ:\n{r.stderr[:500]}"
                return result
            await _progress("pull", "Образ mtg загружен")

            await _progress("secret", "Генерация секрета...")
            r = await self.ssh.execute(
                f"docker run --rm nineseconds/mtg generate-secret --hex {cfg.domain}",
                timeout=60,
            )
            if not r.ok or not r.stdout.strip():
                result.error = f"Не удалось сгенерировать секрет:\n{r.stderr[:500]}"
                return result
            secret = r.stdout.strip()
            result.secret = secret
            result.domain = cfg.domain
            result.dns = cfg.dns
            result.port = cfg.port
            result.container = cfg.container
            await _progress("secret", "Секрет сгенерирован")

            await _progress("container", "Запуск контейнера...")
            await self.ssh.execute(f"docker rm -f {cfg.container} 2>/dev/null || true")

            run_cmd = (
                f"docker run -d"
                f" --name {cfg.container}"
                f" --restart always"
                f" -p {cfg.port}:3128"
                f" --dns {cfg.dns}"
                f" nineseconds/mtg simple-run"
                f" -n {cfg.dns}"
                f" -i {cfg.ip_mode}"
                f" 0.0.0.0:3128"
                f" {secret}"
            )
            r = await self.ssh.execute(run_cmd, timeout=60)
            if not r.ok:
                result.error = f"Не удалось запустить контейнер:\n{r.stderr[:500]}"
                return result

            # Wait for container
            r = await self.ssh.execute(
                f"for i in $(seq 1 10); do"
                f"  docker ps --format '{{{{.Names}}}}' | grep -qw {cfg.container} && exit 0;"
                f"  sleep 1;"
                f" done; exit 1"
            )
            if not r.ok:
                result.error = "Контейнер не запустился за 10 секунд"
                return result
            await _progress("container", "Контейнер запущен")

            await _progress("firewall", "Настройка файрвола...")
            await self.ssh.execute(
                f"command -v ufw &>/dev/null && ufw allow {cfg.port}/tcp 2>/dev/null;"
                f" command -v firewall-cmd &>/dev/null"
                f" && firewall-cmd --permanent --add-port={cfg.port}/tcp 2>/dev/null"
                f" && firewall-cmd --reload 2>/dev/null;"
                f" true"
            )
            await _progress("firewall", "Файрвол настроен")

            await _progress("config", "Сохранение конфигурации...")
            config_content = (
                f"SERVER_IP={result.server_ip}\n"
                f"EXT_PORT={cfg.port}\n"
                f"INTERNAL_PORT=3128\n"
                f"FAKE_DOMAIN={cfg.domain}\n"
                f"DNS_SERVER={cfg.dns}\n"
                f"IP_PREFER={cfg.ip_mode}\n"
                f"CONTAINER_NAME={cfg.container}\n"
                f"SECRET={secret}\n"
            )
            await self.ssh.execute("mkdir -p /etc/mtproto-proxy")
            await self.ssh.upload_string(config_content, "/etc/mtproto-proxy/config")

            ip = result.server_ip
            result.tme_link = f"https://t.me/proxy?server={ip}&port={cfg.port}&secret={secret}"
            result.tg_link = f"tg://proxy?server={ip}&port={cfg.port}&secret={secret}"
            result.status = "running"

            await _progress("done", "Установка завершена!")

        except Exception as e:
            logger.exception("Installation failed")
            result.error = str(e)

        return result

    async def get_status(self, container: str = DEFAULT_CONTAINER) -> ProxyInfo:
        """Get current proxy status from remote server."""
        result = ProxyInfo()

        r = await self.ssh.execute("cat /etc/mtproto-proxy/config 2>/dev/null")
        if r.ok:
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "SERVER_IP":
                        result.server_ip = v
                    elif k == "EXT_PORT":
                        result.port = int(v) if v.isdigit() else 443
                    elif k == "SECRET":
                        result.secret = v
                    elif k == "FAKE_DOMAIN":
                        result.domain = v
                    elif k == "DNS_SERVER":
                        result.dns = v
                    elif k == "CONTAINER_NAME":
                        result.container = v

        r = await self.ssh.execute(f"docker ps --format '{{{{.Names}}}}' 2>/dev/null | grep -qw {container}")
        result.status = "running" if r.ok else "stopped"

        if result.server_ip and result.secret:
            result.tme_link = (
                f"https://t.me/proxy?server={result.server_ip}&port={result.port}&secret={result.secret}"
            )
            result.tg_link = (
                f"tg://proxy?server={result.server_ip}&port={result.port}&secret={result.secret}"
            )

        return result

    async def uninstall(self, container: str = DEFAULT_CONTAINER) -> str:
        """Remove proxy container and config."""
        messages = []

        r = await self.ssh.execute(f"docker rm -f {container} 2>/dev/null")
        messages.append("Контейнер удалён" if r.ok else "Контейнер не найден")

        r = await self.ssh.execute("cat /etc/mtproto-proxy/config 2>/dev/null | grep EXT_PORT")
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

        await self.ssh.execute(f"docker rmi nineseconds/mtg 2>/dev/null || true")
        messages.append("Docker-образ удалён")

        return "\n".join(f"✓ {m}" for m in messages)

    async def restart(self, container: str = DEFAULT_CONTAINER) -> bool:
        r = await self.ssh.execute(f"docker restart {container}")
        return r.ok

    async def update(self, container: str = DEFAULT_CONTAINER) -> ProxyInfo:
        """Pull latest image and restart with saved config."""
        status = await self.get_status(container)
        if not status.secret:
            status.error = "Конфигурация не найдена на сервере"
            return status

        r = await self.ssh.execute("docker pull nineseconds/mtg", timeout=INSTALL_TIMEOUT)
        if not r.ok:
            status.error = f"Не удалось обновить образ:\n{r.stderr[:300]}"
            return status

        await self.ssh.execute(f"docker rm -f {container} 2>/dev/null")

        r = await self.ssh.execute("cat /etc/mtproto-proxy/config 2>/dev/null")
        cfg_vars: dict = {}
        if r.ok:
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg_vars[k.strip()] = v.strip()

        ip_mode = cfg_vars.get("IP_PREFER", DEFAULT_IP_MODE)
        dns = cfg_vars.get("DNS_SERVER", DEFAULT_DNS)
        port = cfg_vars.get("EXT_PORT", str(DEFAULT_PORT))
        internal = cfg_vars.get("INTERNAL_PORT", "3128")

        run_cmd = (
            f"docker run -d"
            f" --name {container}"
            f" --restart always"
            f" -p {port}:{internal}"
            f" --dns {dns}"
            f" nineseconds/mtg simple-run"
            f" -n {dns}"
            f" -i {ip_mode}"
            f" 0.0.0.0:{internal}"
            f" {status.secret}"
        )
        r = await self.ssh.execute(run_cmd, timeout=60)
        if not r.ok:
            status.error = f"Не удалось перезапустить:\n{r.stderr[:300]}"
            return status

        status.status = "running"
        return status
