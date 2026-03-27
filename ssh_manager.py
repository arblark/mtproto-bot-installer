import asyncio
import io
import logging
from dataclasses import dataclass

import paramiko

from config import SSH_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass
class SSHResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SSHManager:
    """Manages SSH connections to remote servers."""

    def __init__(self, host: str, port: int, username: str, password: str | None = None, key: str | None = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key = key
        self._client: paramiko.SSHClient | None = None

    def _get_pkey(self) -> paramiko.PKey | None:
        if not self.key:
            return None
        for key_class in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
            try:
                return key_class.from_private_key(io.StringIO(self.key))
            except Exception:
                continue
        raise ValueError("Не удалось распознать формат SSH-ключа")

    async def connect(self) -> None:
        def _connect():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs: dict = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": SSH_TIMEOUT,
                "allow_agent": False,
                "look_for_keys": False,
            }
            pkey = self._get_pkey()
            if pkey:
                kwargs["pkey"] = pkey
            elif self.password:
                kwargs["password"] = self.password
            client.connect(**kwargs)
            return client

        self._client = await asyncio.get_event_loop().run_in_executor(None, _connect)

    async def execute(self, command: str, timeout: int = 60) -> SSHResult:
        if not self._client:
            raise RuntimeError("SSH не подключён")

        def _exec():
            stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return SSHResult(
                exit_code=exit_code,
                stdout=stdout.read().decode("utf-8", errors="replace"),
                stderr=stderr.read().decode("utf-8", errors="replace"),
            )

        return await asyncio.get_event_loop().run_in_executor(None, _exec)

    async def upload_string(self, content: str, remote_path: str) -> None:
        if not self._client:
            raise RuntimeError("SSH не подключён")

        def _upload():
            sftp = self._client.open_sftp()
            with sftp.file(remote_path, "w") as f:
                f.write(content)
            sftp.close()

        await asyncio.get_event_loop().run_in_executor(None, _upload)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        self.close()
