"""Network diagnostics for IT support."""
from __future__ import annotations

import platform
import socket
import subprocess
import time

import psutil

COMMON_PORTS = {21: "FTP", 22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3",
                143: "IMAP", 443: "HTTPS", 445: "SMB", 3306: "MySQL", 3389: "RDP",
                5432: "PostgreSQL", 8080: "HTTP-alt"}


def interfaces() -> list[dict]:
    stats = psutil.net_if_stats()
    out = []
    for name, addrs in psutil.net_if_addrs().items():
        ipv4 = next((a.address for a in addrs if a.family == socket.AF_INET), "")
        ipv6 = next((a.address for a in addrs if a.family == socket.AF_INET6), "")
        mac = next((a.address for a in addrs if a.family == psutil.AF_LINK), "")
        st = stats.get(name)
        out.append({"name": name, "ipv4": ipv4, "ipv6": ipv6.split("%")[0], "mac": mac,
                    "up": bool(st and st.isup), "speed": st.speed if st else 0})
    return out


def ping(host: str, count: int = 4, timeout: int = 15) -> str:
    _validate_host(host)
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        r = subprocess.run(["ping", flag, str(count), host], capture_output=True,
                           text=True, timeout=timeout + count * 2)
        return (r.stdout or r.stderr).strip() or "Sem saída do ping."
    except FileNotFoundError:
        return "Comando ping não encontrado neste sistema."
    except subprocess.TimeoutExpired:
        return "Tempo esgotado."


def dns_lookup(host: str) -> str:
    _validate_host(host)
    try:
        name, aliases, addrs = socket.gethostbyname_ex(host)
        return f"{name}\n" + "\n".join(addrs)
    except socket.gaierror as e:
        return f"Falha na resolução DNS: {e}"


def check_ports(host: str, ports: list[int] | None = None, timeout: float = 0.8) -> list[dict]:
    """TCP connect check. Use only on hosts you own or are authorized to test."""
    _validate_host(host)
    out = []
    for port in ports or list(COMMON_PORTS):
        s = socket.socket()
        s.settimeout(timeout)
        t0 = time.time()
        try:
            s.connect((host, port))
            state = "aberta"
        except (socket.timeout, OSError):
            state = "fechada/filtrada"
        finally:
            s.close()
        out.append({"port": port, "service": COMMON_PORTS.get(port, ""), "state": state,
                    "ms": round((time.time() - t0) * 1000)})
    return out


def listening_ports() -> list[dict]:
    out = []
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        return out
    for c in conns:
        if c.status == psutil.CONN_LISTEN and c.laddr:
            name = ""
            if c.pid:
                try:
                    name = psutil.Process(c.pid).name()
                except psutil.Error:
                    pass
            out.append({"port": c.laddr.port, "address": c.laddr.ip, "pid": c.pid or 0, "process": name})
    return sorted(out, key=lambda x: x["port"])


def _validate_host(host: str) -> None:
    ok = host and len(host) <= 253 and all(ch.isalnum() or ch in ".-:" for ch in host) \
        and not host.startswith("-")
    if not ok:
        raise ValueError("Host inválido.")
