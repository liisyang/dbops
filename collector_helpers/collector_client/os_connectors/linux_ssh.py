"""Linux SSH connector — paramiko.

Connects via SSH to Linux hosts and runs read-only commands.
Supports both key-based and password-based authentication.

Commands executed (read-only):
  hostname, hostname -f, uname -r/-m, cat /etc/os-release,
  nproc, free -b, cat /proc/uptime, ip -4 route get 8.8.8.8
"""

from __future__ import annotations

import io
from typing import Any

from collector_client.os_connectors.base import BaseOsConnector


class LinuxSshConnector(BaseOsConnector):
    """Linux SSH fact collector.

    Connects using paramiko SSH.
    Requires: paramiko>=3.0

    Authentication priority:
    1. Private key (if DBOPS_OS_PRIVATE_KEY is set)
    2. Password (if DBOPS_OS_PASSWORD is set)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = None

    def _connect(self) -> None:
        """Establish SSH connection if not already connected."""
        if self._client is not None:
            return

        import paramiko

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": self.timeout_seconds,
        }

        # Prefer private key over password
        if self.private_key:
            key_file = io.StringIO(self.private_key)
            try:
                pkey = paramiko.RSAKey.from_private_key(key_file)
                connect_kwargs["pkey"] = pkey
            except Exception:
                # Try other key types
                key_file.seek(0)
                try:
                    pkey = paramiko.Ed25519Key.from_private_key(key_file)
                    connect_kwargs["pkey"] = pkey
                except Exception:
                    key_file.seek(0)
                    try:
                        pkey = paramiko.ECDSAKey.from_private_key(key_file)
                        connect_kwargs["pkey"] = pkey
                    except Exception:
                        pass
        elif self.password:
            connect_kwargs["password"] = self.password

        self._client.connect(**connect_kwargs)

    def _run_command(self, command: str) -> tuple[str, str, int]:
        """Run a single command and return (stdout, stderr, exit_code)."""
        self._connect()
        _, stdout, stderr = self._client.exec_command(command, timeout=self.timeout_seconds)
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        return out, err, exit_code

    def test_connection(self) -> bool:
        try:
            self._connect()
            _, _, exit_code = self._run_command("echo ok")
            return exit_code == 0
        except Exception:
            return False

    def collect_basic_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}

        # hostname
        out, _, _ = self._run_command("hostname")
        if out:
            facts["hostname"] = out

        # fqdn
        out, _, _ = self._run_command("hostname -f")
        if out:
            facts["fqdn"] = out

        # CPU cores
        out, _, _ = self._run_command("nproc")
        if out:
            try:
                facts["cpu_cores"] = int(out.strip())
            except ValueError:
                facts["cpu_cores_raw"] = out.strip()

        # Memory (in MB for consistency)
        out, _, _ = self._run_command("free -b | awk '/^Mem:/{print $2}'")
        if out:
            try:
                facts["memory_mb"] = int(out.strip()) // (1024 * 1024)
            except ValueError:
                facts["memory_raw"] = out.strip()

        # Uptime
        out, _, _ = self._run_command("cat /proc/uptime | awk '{print $1}'")
        if out:
            try:
                facts["uptime_seconds"] = float(out.strip().split()[0])
            except (ValueError, IndexError):
                facts["uptime_raw"] = out.strip()

        # Primary IP
        out, _, _ = self._run_command(
            "ip -4 route get 8.8.8.8 | awk '{print $7}' | head -1"
        )
        if out:
            facts["primary_ip"] = out.strip()

        # OS release info
        out, _, _ = self._run_command(
            "cat /etc/os-release | grep -E '^(ID|VERSION_ID|PRETTY_NAME)=' | "
            "sed 's/\"//g'"
        )
        if out:
            for line in out.split("\n"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    facts[key.lower()] = val.strip()

        return facts

    def collect_version_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}

        # Kernel version
        out, _, _ = self._run_command("uname -r")
        if out:
            facts["kernel_version"] = out.strip()

        # Kernel release
        out, _, _ = self._run_command("uname -a")
        if out:
            facts["kernel_full"] = out.strip()

        # Architecture
        out, _, _ = self._run_command("uname -m")
        if out:
            facts["architecture"] = out.strip()

        # OS release (detailed)
        out, _, _ = self._run_command("cat /etc/os-release")
        if out:
            facts["os_release_raw"] = out.strip()

        # Kernel build info from /proc/version
        out, _, _ = self._run_command("cat /proc/version")
        if out:
            facts["kernel_build"] = out.strip()

        return facts

    def collect_role_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        facts["os_role"] = "host"

        # Check if running in a container
        out, _, _ = self._run_command(
            "test -f /.dockerenv && echo docker || "
            "grep -q container=lxc /proc/1/environ 2>/dev/null && echo lxc || "
            "echo bare_metal"
        )
        if out:
            facts["runtime_type"] = out.strip()

        # Check virtualization via systemd-detect-virt
        out, _, _ = self._run_command("systemd-detect-virt 2>/dev/null || echo none")
        if out:
            facts["virtualization"] = out.strip()

        return facts

    def close(self) -> None:
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._client = None
