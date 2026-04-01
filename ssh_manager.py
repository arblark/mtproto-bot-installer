from __future__ import annotations

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

    async def execute_stream(
        self, command: str, timeout: int = 600, on_output: callable = None,
    ) -> SSHResult:
        """Execute command and call on_output(line) for each line of stdout."""
        if not self._client:
            raise RuntimeError("SSH не подключён")

        def _exec():
            transport = self._client.get_transport()
            channel = transport.open_session()
            channel.settimeout(timeout)
            channel.exec_command(command)

            stdout_chunks = []
            stderr_chunks = []
            buf = ""

            while True:
                if channel.recv_ready():
                    data = channel.recv(4096).decode("utf-8", errors="replace")
                    stdout_chunks.append(data)
                    if on_output:
                        buf += data
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            line = line.strip()
                            if line:
                                on_output(line)
                if channel.recv_stderr_ready():
                    stderr_chunks.append(
                        channel.recv_stderr(4096).decode("utf-8", errors="replace")
                    )
                if channel.exit_status_ready():
                    while channel.recv_ready():
                        data = channel.recv(4096).decode("utf-8", errors="replace")
                        stdout_chunks.append(data)
                        if on_output:
                            buf += data
                            while "\n" in buf:
                                line, buf = buf.split("\n", 1)
                                line = line.strip()
                                if line:
                                    on_output(line)
                    while channel.recv_stderr_ready():
                        stderr_chunks.append(
                            channel.recv_stderr(4096).decode("utf-8", errors="replace")
                        )
                    break
                import time
                time.sleep(0.1)

            if on_output and buf.strip():
                on_output(buf.strip())

            return SSHResult(
                exit_code=channel.recv_exit_status(),
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
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
