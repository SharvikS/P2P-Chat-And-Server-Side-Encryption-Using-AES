#!/usr/bin/env python3
"""
NetChat Server v2.0  —  AES-encrypted P2P relay with user management.
Usage: python server.py [--host 0.0.0.0] [--port 65432]
"""

import argparse
import datetime
import json
import os
import re
import socket
import struct
import threading
from collections import deque
from typing import Dict, Optional

import config as cfg
from crypto_utils import get_cipher, encrypt_bytes, decrypt_bytes

# ── ANSI colours (server terminal only) ──────────────────────────────────────
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"
    GREEN = "\033[92m"; CYAN = "\033[96m"; YELLOW = "\033[93m"
    RED = "\033[91m";   GRAY = "\033[90m"; MAGENTA = "\033[95m"

cipher = get_cipher()
clients: Dict[socket.socket, dict] = {}   # conn → {username, addr}
lock    = threading.Lock()
history: deque = deque(maxlen=cfg.MAX_HISTORY)


# ── Wire protocol (length-prefixed JSON + optional binary blob) ───────────────

def _send(sock: socket.socket, payload: dict, blob: bytes = b"") -> None:
    j = json.dumps(payload).encode()
    sock.sendall(struct.pack(">II", len(j), len(blob)) + j + blob)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def _recv(sock: socket.socket):
    hdr = _recv_exact(sock, 8)
    jlen, blen = struct.unpack(">II", hdr)
    payload = json.loads(_recv_exact(sock, jlen))
    blob = _recv_exact(sock, blen) if blen else b""
    return payload, blob


# ── Broadcast / routing helpers ───────────────────────────────────────────────

def _broadcast(payload: dict, blob: bytes = b"", exclude=None) -> None:
    with lock:
        targets = list(clients.keys())
    dead = []
    for conn in targets:
        if conn is exclude:
            continue
        try:
            _send(conn, payload, blob)
        except OSError:
            dead.append(conn)
    for conn in dead:
        _evict(conn)


def _send_to(username: str, payload: dict, blob: bytes = b"") -> bool:
    with lock:
        conn = next((c for c, i in clients.items() if i["username"] == username), None)
    if conn:
        try:
            _send(conn, payload, blob)
            return True
        except OSError:
            _evict(conn)
    return False


def _evict(conn: socket.socket) -> Optional[str]:
    with lock:
        info = clients.pop(conn, None)
    if info:
        try:
            conn.close()
        except OSError:
            pass
        return info["username"]
    return None


def _push_user_list() -> None:
    with lock:
        users = [i["username"] for i in clients.values()]
    _broadcast({"type": "user_list", "users": users})


# ── Utilities ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M")


def _fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n} GB"


def _log(msg: str) -> None:
    t = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"{C.GRAY}[{t}]{C.RESET} {msg}")


# ── Per-client handler thread ─────────────────────────────────────────────────

def handle_client(conn: socket.socket, addr: tuple) -> None:
    username: Optional[str] = None
    try:
        payload, _ = _recv(conn)
        if payload.get("type") != "join":
            conn.close()
            return

        username = str(payload.get("username", "")).strip()
        if not re.match(r"^[A-Za-z0-9_]{1,20}$", username):
            _send(conn, {"type": "join_ack", "status": "error",
                         "message": "Username must be 1–20 chars: letters, digits, underscores."})
            conn.close()
            return

        with lock:
            taken = [i["username"] for i in clients.values()]
            if username in taken:
                _send(conn, {"type": "join_ack", "status": "error",
                             "message": f'"{username}" is already taken.'})
                conn.close()
                return
            clients[conn] = {"username": username, "addr": addr}

        _send(conn, {"type": "join_ack", "status": "ok",
                     "username": username, "history": list(history)})

        sys_msg = {"type": "system", "content": f"{username} joined the chat",
                   "timestamp": _now()}
        history.append(sys_msg)
        _broadcast(sys_msg, exclude=conn)
        _push_user_list()
        _log(f"[{C.GREEN}+{C.RESET}] {C.BOLD}{username}{C.RESET} @ {addr[0]}:{addr[1]}")

        # ── Message loop ──────────────────────────────────────────────────────
        while True:
            payload, blob = _recv(conn)
            t = payload.get("type")

            if t == "chat":
                content = payload.get("content", "").strip()
                if not content:
                    continue
                msg = {"type": "chat", "sender": username,
                       "content": content, "timestamp": _now()}
                history.append(msg)
                _broadcast(msg)
                _log(f"[{C.CYAN}MSG{C.RESET}] {username}: {content[:100]}")

            elif t == "dm":
                target  = payload.get("target", "")
                content = payload.get("content", "").strip()
                ts = _now()
                if _send_to(target, {"type": "dm", "sender": username,
                                     "content": content, "timestamp": ts}):
                    _send(conn, {"type": "dm_echo", "target": target,
                                 "content": content, "timestamp": ts})
                    _log(f"[{C.MAGENTA}DM{C.RESET}] {username} → {target}")
                else:
                    _send(conn, {"type": "system",
                                 "content": f'User "{target}" is not online.',
                                 "timestamp": _now()})

            elif t == "typing":
                _broadcast({"type": "typing", "username": username,
                             "state": payload.get("state", False)}, exclude=conn)

            elif t == "file_upload":
                if not blob:
                    continue
                fname = os.path.basename(payload.get("filename", "file"))
                fsize = payload.get("filesize", len(blob))
                enc   = encrypt_bytes(cipher, blob)
                os.makedirs(cfg.STORAGE_DIR, exist_ok=True)
                with open(os.path.join(cfg.STORAGE_DIR, fname + ".enc"), "wb") as f:
                    f.write(enc)
                notif = {"type": "file_notification", "filename": fname,
                         "sender": username, "filesize": fsize, "timestamp": _now()}
                history.append(notif)
                _broadcast(notif)
                _log(f"[{C.YELLOW}FILE{C.RESET}] {username} uploaded {fname!r} ({_fmt(fsize)})")

            elif t == "file_download":
                fname = os.path.basename(payload.get("filename", ""))
                path  = os.path.join(cfg.STORAGE_DIR, fname + ".enc")
                if not os.path.exists(path):
                    _send(conn, {"type": "system",
                                 "content": f'File "{fname}" not found on server.',
                                 "timestamp": _now()})
                    continue
                with open(path, "rb") as f:
                    enc = f.read()
                _send(conn, {"type": "file_download_start", "filename": fname,
                             "filesize": len(enc)}, enc)
                _log(f"[{C.YELLOW}FILE{C.RESET}] {username} downloaded {fname!r}")

            elif t == "get_files":
                os.makedirs(cfg.STORAGE_DIR, exist_ok=True)
                files = [fn[:-4] for fn in os.listdir(cfg.STORAGE_DIR)
                         if fn.endswith(".enc")]
                _send(conn, {"type": "file_list", "files": files})

    except (ConnectionError, OSError, struct.error, json.JSONDecodeError):
        pass
    finally:
        _evict(conn)
        if username:
            sys_msg = {"type": "system", "content": f"{username} left the chat",
                       "timestamp": _now()}
            history.append(sys_msg)
            _broadcast(sys_msg)
            _push_user_list()
            _log(f"[{C.RED}-{C.RESET}] {C.BOLD}{username}{C.RESET} disconnected")


# ── Entry point ───────────────────────────────────────────────────────────────

def start(host: str, port: int) -> None:
    os.makedirs(cfg.STORAGE_DIR, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen()
        print(f"\n{'─'*46}")
        print(f"  {C.BOLD}{C.CYAN}NetChat Server v2.0{C.RESET}")
        print(f"  {C.GREEN}●{C.RESET} Listening on {C.BOLD}{host}:{port}{C.RESET}")
        print(f"  {C.YELLOW}🔐{C.RESET} AES-128 Fernet encryption  |  LAN-ready")
        print(f"  {C.GRAY}Files stored in: {cfg.STORAGE_DIR}/{C.RESET}")
        print(f"{'─'*46}\n")
        try:
            while True:
                conn, addr = srv.accept()
                threading.Thread(target=handle_client, args=(conn, addr),
                                 daemon=True).start()
        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}Shutting down.{C.RESET}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NetChat Server")
    ap.add_argument("--host", default=cfg.HOST)
    ap.add_argument("--port", type=int, default=cfg.PORT)
    a = ap.parse_args()
    start(a.host, a.port)
