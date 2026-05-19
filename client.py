#!/usr/bin/env python3
"""
NetChat Client v2.0  —  Modern dark GUI with AES-encrypted messaging & file transfers.
Usage: python client.py [--host 127.0.0.1] [--port 65432]
"""

import argparse
import json
import os
import re
import socket
import struct
import threading
import time
from queue import Empty, Queue
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk
import tkinter as tk

import config as cfg
from crypto_utils import get_cipher, decrypt_bytes

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG   = "#1a1b26"
BG2  = "#24283b"
BG3  = "#16161e"
BORD = "#3b4261"
FG   = "#c0caf5"
DIM  = "#565f89"
BLUE = "#7aa2f7"
CYAN = "#7dcfff"
GRN  = "#9ece6a"
YLW  = "#e0af68"
RED  = "#f7768e"
MAG  = "#bb9af7"
ORG  = "#ff9e64"

USER_COLORS = [BLUE, CYAN, GRN, YLW, ORG, MAG, RED]
_color_map: dict = {}


def _user_color(name: str) -> str:
    if name not in _color_map:
        _color_map[name] = USER_COLORS[len(_color_map) % len(USER_COLORS)]
    return _color_map[name]


# ── Wire protocol (mirrors server) ────────────────────────────────────────────

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


# ── Login window ──────────────────────────────────────────────────────────────

class LoginWindow(ctk.CTk):
    def __init__(self, default_host: str, default_port: int):
        super().__init__()
        self.title("NetChat — Connect")
        self.geometry("400x340")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.result: Optional[tuple] = None

        ctk.CTkLabel(self, text="NetChat", font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=BLUE).pack(pady=(36, 2))
        ctk.CTkLabel(self, text="AES-Encrypted P2P Chat",
                     font=ctk.CTkFont(size=12), text_color=DIM).pack(pady=(0, 28))

        frame = ctk.CTkFrame(self, fg_color=BG2, corner_radius=12)
        frame.pack(fill="x", padx=32, pady=4)

        def _row(label, default, row):
            ctk.CTkLabel(frame, text=label, text_color=DIM,
                         font=ctk.CTkFont(size=11)).grid(row=row, column=0,
                         sticky="w", padx=16, pady=(12, 0))
            e = ctk.CTkEntry(frame, fg_color=BG3, border_color=BORD,
                             text_color=FG, height=36, corner_radius=8)
            e.insert(0, default)
            e.grid(row=row+1, column=0, sticky="ew", padx=16, pady=(2, 12))
            return e

        frame.columnconfigure(0, weight=1)
        self._name  = _row("Username", "", 0)
        self._host  = _row("Server Host", default_host, 2)
        self._port  = _row("Port", str(default_port), 4)

        self._btn = ctk.CTkButton(
            self, text="Connect", height=42, corner_radius=10,
            fg_color=BLUE, hover_color="#5d8ef0", text_color=BG,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._connect)
        self._btn.pack(fill="x", padx=32, pady=16)

        self._err = ctk.CTkLabel(self, text="", text_color=RED,
                                  font=ctk.CTkFont(size=11))
        self._err.pack()

        self._name.bind("<Return>", lambda _: self._connect())
        self._host.bind("<Return>", lambda _: self._connect())
        self._port.bind("<Return>", lambda _: self._connect())
        self._name.focus()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _connect(self):
        name = self._name.get().strip()
        host = self._host.get().strip()
        port_s = self._port.get().strip()
        if not re.match(r"^[A-Za-z0-9_]{1,20}$", name):
            self._err.configure(text="Username: 1–20 letters, digits, or underscores.")
            return
        if not host:
            self._err.configure(text="Enter a server host.")
            return
        try:
            port = int(port_s)
            assert 1 <= port <= 65535
        except (ValueError, AssertionError):
            self._err.configure(text="Port must be 1–65535.")
            return
        self.result = (name, host, port)
        self.destroy()


# ── Main chat window ──────────────────────────────────────────────────────────

class ChatApp(ctk.CTk):
    def __init__(self, username: str, host: str, port: int):
        super().__init__()
        self.username = username
        self.host     = host
        self.port     = port
        self.cipher   = get_cipher()
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._typing_timer: Optional[str] = None
        self._is_typing = False
        self._ui_q: Queue = Queue()
        self._typing_users: set = set()
        self._server_files: list = []

        self.title(f"NetChat  —  {username}")
        self.geometry("1000x660")
        self.minsize(760, 500)
        self.configure(fg_color=BG)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(40, self._drain_queue)
        self._connect()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header bar
        hdr = ctk.CTkFrame(self, fg_color=BG2, height=48, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._status_dot = ctk.CTkLabel(hdr, text="●", text_color=RED,
                                         font=ctk.CTkFont(size=14))
        self._status_dot.pack(side="left", padx=(16, 4))
        ctk.CTkLabel(hdr, text="NetChat", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=FG).pack(side="left")
        self._status_lbl = ctk.CTkLabel(hdr, text="Connecting…",
                                         font=ctk.CTkFont(size=11), text_color=DIM)
        self._status_lbl.pack(side="left", padx=10)

        ctk.CTkLabel(hdr, text=f"🔐 AES-128",
                     font=ctk.CTkFont(size=10), text_color=DIM).pack(side="right", padx=16)
        ctk.CTkLabel(hdr, text=f"{self.host}:{self.port}",
                     font=ctk.CTkFont(size=10), text_color=DIM).pack(side="right", padx=(0, 8))

        # Body: sidebar + chat
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left sidebar
        sidebar = ctk.CTkFrame(body, fg_color=BG2, width=190, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="ONLINE", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=DIM).pack(anchor="w", padx=14, pady=(14, 4))

        self._user_frame = ctk.CTkScrollableFrame(
            sidebar, fg_color=BG2, scrollbar_button_color=BG3, height=220)
        self._user_frame.pack(fill="x", padx=6)

        ctk.CTkFrame(sidebar, fg_color=BORD, height=1, corner_radius=0).pack(
            fill="x", padx=10, pady=10)

        ctk.CTkLabel(sidebar, text="SERVER FILES", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=DIM).pack(anchor="w", padx=14, pady=(0, 4))

        self._file_frame = ctk.CTkScrollableFrame(
            sidebar, fg_color=BG2, scrollbar_button_color=BG3)
        self._file_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        ctk.CTkButton(sidebar, text="⟳ Refresh Files", height=30,
                      fg_color=BG3, hover_color=BORD, text_color=DIM,
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=self._req_file_list).pack(fill="x", padx=10, pady=(0, 10))

        # Right: chat area
        chat_col = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        chat_col.grid(row=0, column=1, sticky="nsew")
        chat_col.rowconfigure(0, weight=1)
        chat_col.columnconfigure(0, weight=1)

        # Message display (plain tk.Text for full tag support)
        txt_frame = ctk.CTkFrame(chat_col, fg_color=BG3, corner_radius=0)
        txt_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        txt_frame.rowconfigure(0, weight=1)
        txt_frame.columnconfigure(0, weight=1)

        self._chat = tk.Text(
            txt_frame, state="disabled", wrap="word", cursor="arrow",
            bg=BG3, fg=FG, font=("Segoe UI", 11), bd=0, relief="flat",
            padx=14, pady=10, selectbackground=BG2, selectforeground=FG,
            insertbackground=FG, spacing1=2, spacing3=6)
        self._chat.grid(row=0, column=0, sticky="nsew")

        sb = tk.Scrollbar(txt_frame, command=self._chat.yview, bg=BG3,
                          troughcolor=BG3, bd=0, relief="flat", width=8)
        sb.grid(row=0, column=1, sticky="ns")
        self._chat.configure(yscrollcommand=sb.set)

        self._define_tags()

        # Typing indicator
        self._typing_lbl = ctk.CTkLabel(chat_col, text="", text_color=DIM,
                                         font=ctk.CTkFont(size=10, slant="italic"),
                                         height=16, anchor="w")
        self._typing_lbl.grid(row=1, column=0, sticky="ew", padx=14)

        # Input bar
        inp = ctk.CTkFrame(chat_col, fg_color=BG2, height=60, corner_radius=0)
        inp.grid(row=2, column=0, sticky="ew")
        inp.pack_propagate(False)
        inp.columnconfigure(1, weight=1)

        ctk.CTkButton(inp, text="📎", width=40, height=36, fg_color=BG3,
                      hover_color=BORD, text_color=YLW, corner_radius=8,
                      font=ctk.CTkFont(size=16), command=self._upload_file
                      ).grid(row=0, column=0, padx=(10, 4), pady=12)

        self._entry = ctk.CTkEntry(
            inp, placeholder_text='Message… or /help for commands',
            fg_color=BG3, border_color=BORD, text_color=FG,
            placeholder_text_color=DIM, height=36, corner_radius=8,
            font=ctk.CTkFont(size=12))
        self._entry.grid(row=0, column=1, sticky="ew", padx=4, pady=12)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<KeyRelease>", self._on_key_release)

        self._send_btn = ctk.CTkButton(
            inp, text="Send", width=72, height=36,
            fg_color=BLUE, hover_color="#5d8ef0", text_color=BG,
            font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
            command=self._send_message)
        self._send_btn.grid(row=0, column=2, padx=(4, 10), pady=12)

    def _define_tags(self):
        t = self._chat
        t.tag_configure("system",    foreground=DIM,  font=("Segoe UI", 10, "italic"),
                         justify="center", spacing1=4, spacing3=4)
        t.tag_configure("timestamp", foreground=DIM,  font=("Segoe UI", 9))
        t.tag_configure("self_name", foreground=CYAN, font=("Segoe UI", 11, "bold"))
        t.tag_configure("self_msg",  foreground=FG)
        t.tag_configure("dm_name",   foreground=MAG,  font=("Segoe UI", 11, "bold"))
        t.tag_configure("dm_msg",    foreground=MAG)
        t.tag_configure("file_note", foreground=YLW,  font=("Segoe UI", 10))
        t.tag_configure("err",       foreground=RED,  font=("Segoe UI", 10))
        t.tag_configure("help",      foreground=GRN,  font=("Segoe UI", 10))
        # Dynamic per-user tags created on first use

    def _user_tag(self, name: str) -> str:
        tag = f"user_{name}"
        if tag not in self._chat.tag_names():
            self._chat.tag_configure(tag, foreground=_user_color(name),
                                     font=("Segoe UI", 11, "bold"))
        return tag

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self):
        def _try():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.host, self.port))
                _send(sock, {"type": "join", "username": self.username})
                payload, _ = _recv(sock)
                if payload.get("status") != "ok":
                    self._q("_show_error", payload.get("message", "Join rejected."))
                    sock.close()
                    return
                self._sock = sock
                self._connected = True
                self._q("_on_connected")
                for msg in payload.get("history", []):
                    self._q("_render", msg)
                threading.Thread(target=self._recv_loop, daemon=True).start()
            except (OSError, ConnectionError) as e:
                self._q("_show_error", f"Cannot connect to {self.host}:{self.port} — {e}")
        threading.Thread(target=_try, daemon=True).start()

    def _recv_loop(self):
        try:
            while True:
                payload, blob = _recv(self._sock)
                self._q("_handle", payload, blob)
        except (ConnectionError, OSError):
            self._q("_on_disconnected")

    # ── Queue bridge (background → main thread) ───────────────────────────────

    def _q(self, method: str, *args):
        self._ui_q.put((method, args))

    def _drain_queue(self):
        try:
            while True:
                method, args = self._ui_q.get_nowait()
                getattr(self, method)(*args)
        except Empty:
            pass
        self.after(40, self._drain_queue)

    # ── Packet handler (runs on main thread via queue) ────────────────────────

    def _handle(self, payload: dict, blob: bytes):
        t = payload.get("type")
        if t == "chat":
            self._render(payload)
        elif t == "system":
            self._render(payload)
        elif t == "dm":
            self._render(payload)
        elif t == "dm_echo":
            payload["type"] = "dm_echo"
            self._render(payload)
        elif t == "file_notification":
            self._render(payload)
            self._req_file_list()
        elif t == "file_download_start":
            self._save_download(payload, blob)
        elif t == "user_list":
            self._refresh_users(payload.get("users", []))
        elif t == "file_list":
            self._refresh_files(payload.get("files", []))
        elif t == "typing":
            self._handle_typing(payload)

    def _render(self, msg: dict):
        t   = msg.get("type")
        ts  = msg.get("timestamp", "")
        c   = self._chat
        c.configure(state="normal")

        if t == "system":
            c.insert("end", f"\n── {msg.get('content', '')} ──\n", "system")

        elif t == "chat":
            sender  = msg.get("sender", "?")
            content = msg.get("content", "")
            if sender == self.username:
                c.insert("end", f"You", "self_name")
            else:
                c.insert("end", sender, self._user_tag(sender))
            c.insert("end", f"  {ts}\n", "timestamp")
            c.insert("end", f"{content}\n\n", "self_msg")

        elif t in ("dm", "dm_echo"):
            if t == "dm":
                label = f"[DM] {msg.get('sender', '?')}"
            else:
                label = f"[DM → {msg.get('target', '?')}]"
            c.insert("end", f"{label}", "dm_name")
            c.insert("end", f"  {ts}\n", "timestamp")
            c.insert("end", f"{msg.get('content', '')}\n\n", "dm_msg")

        elif t == "file_notification":
            sender = msg.get("sender", "?")
            fname  = msg.get("filename", "?")
            fsize  = msg.get("filesize", 0)
            size_s = _fmt_size(fsize)
            c.insert("end", f"📎 {sender} shared {fname!r} ({size_s}) — click to download\n",
                     "file_note")
            # Make it clickable
            idx = c.index("end - 2c linestart")
            tag = f"dl_{fname}_{id(msg)}"
            c.tag_add(tag, idx, "end - 1c")
            c.tag_configure(tag, foreground=YLW, underline=True)
            c.tag_bind(tag, "<Button-1>", lambda e, f=fname: self._download_file(f))
            c.tag_bind(tag, "<Enter>",    lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>",    lambda e: c.configure(cursor="arrow"))
            c.insert("end", "\n")

        c.configure(state="disabled")
        c.see("end")

    # ── Status helpers ────────────────────────────────────────────────────────

    def _on_connected(self):
        self._status_dot.configure(text_color=GRN)
        self._status_lbl.configure(text=f"Connected as {self.username}")
        self._entry.configure(state="normal")
        self._send_btn.configure(state="normal")
        self._add_help_hint()
        self._req_file_list()

    def _on_disconnected(self):
        self._connected = False
        self._status_dot.configure(text_color=RED)
        self._status_lbl.configure(text="Disconnected")
        self._entry.configure(state="disabled")
        self._send_btn.configure(state="disabled")
        self._chat.configure(state="normal")
        self._chat.insert("end", "\n── Disconnected from server ──\n", "err")
        self._chat.configure(state="disabled")
        self._chat.see("end")

    def _show_error(self, msg: str):
        messagebox.showerror("NetChat", msg, parent=self)

    def _add_help_hint(self):
        self._chat.configure(state="normal")
        self._chat.insert("end",
            "Type /help for commands  •  Click shared files to download  •  /dm <user> <msg> for DMs\n\n",
            "help")
        self._chat.configure(state="disabled")

    # ── Sidebar helpers ───────────────────────────────────────────────────────

    def _refresh_users(self, users: list):
        for w in self._user_frame.winfo_children():
            w.destroy()
        for u in users:
            color = CYAN if u == self.username else _user_color(u)
            suffix = " (you)" if u == self.username else ""
            btn = ctk.CTkButton(
                self._user_frame, text=f"● {u}{suffix}", anchor="w",
                fg_color="transparent", hover_color=BG3, text_color=color,
                font=ctk.CTkFont(size=12), height=28, corner_radius=6,
                command=(lambda n=u: self._dm_shortcut(n)) if u != self.username else None)
            btn.pack(fill="x", pady=1)

    def _refresh_files(self, files: list):
        self._server_files = files
        for w in self._file_frame.winfo_children():
            w.destroy()
        if not files:
            ctk.CTkLabel(self._file_frame, text="No files yet", text_color=DIM,
                         font=ctk.CTkFont(size=10)).pack(pady=6)
            return
        for f in files:
            btn = ctk.CTkButton(
                self._file_frame, text=f"📄 {f}", anchor="w",
                fg_color="transparent", hover_color=BG3, text_color=YLW,
                font=ctk.CTkFont(size=11), height=26, corner_radius=6,
                command=lambda fn=f: self._download_file(fn))
            btn.pack(fill="x", pady=1)

    def _handle_typing(self, payload: dict):
        user  = payload.get("username", "")
        state = payload.get("state", False)
        if state:
            self._typing_users.add(user)
        else:
            self._typing_users.discard(user)
        if self._typing_users:
            names = ", ".join(sorted(self._typing_users))
            suffix = "is" if len(self._typing_users) == 1 else "are"
            self._typing_lbl.configure(text=f"{names} {suffix} typing…")
        else:
            self._typing_lbl.configure(text="")

    # ── Message input ─────────────────────────────────────────────────────────

    def _on_enter(self, _event=None):
        self._send_message()

    def _on_key_release(self, _event=None):
        if not self._connected:
            return
        if not self._is_typing:
            self._is_typing = True
            try:
                _send(self._sock, {"type": "typing", "state": True})
            except OSError:
                pass
        if self._typing_timer:
            self.after_cancel(self._typing_timer)
        self._typing_timer = self.after(2000, self._stop_typing)

    def _stop_typing(self):
        self._is_typing = False
        self._typing_timer = None
        if self._connected:
            try:
                _send(self._sock, {"type": "typing", "state": False})
            except OSError:
                pass

    def _send_message(self):
        if not self._connected:
            return
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, "end")
        self._stop_typing()

        # Slash commands
        if text.startswith("/"):
            self._handle_command(text)
            return

        try:
            _send(self._sock, {"type": "chat", "content": text})
        except OSError:
            self._on_disconnected()

    def _handle_command(self, text: str):
        parts = text.split(maxsplit=2)
        cmd   = parts[0].lower()

        if cmd == "/help":
            self._chat.configure(state="normal")
            self._chat.insert("end",
                "Commands:\n"
                "  /dm <user> <message>  — direct message\n"
                "  /files                — list server files\n"
                "  /clear                — clear chat display\n"
                "  /help                 — show this help\n\n",
                "help")
            self._chat.configure(state="disabled")
            self._chat.see("end")

        elif cmd == "/clear":
            self._chat.configure(state="normal")
            self._chat.delete("1.0", "end")
            self._chat.configure(state="disabled")

        elif cmd == "/files":
            self._req_file_list()

        elif cmd == "/dm":
            if len(parts) < 3:
                self._chat.configure(state="normal")
                self._chat.insert("end", "Usage: /dm <user> <message>\n", "err")
                self._chat.configure(state="disabled")
                return
            target, content = parts[1], parts[2]
            try:
                _send(self._sock, {"type": "dm", "target": target, "content": content})
            except OSError:
                self._on_disconnected()

        else:
            self._chat.configure(state="normal")
            self._chat.insert("end", f'Unknown command: {cmd}. Type /help.\n', "err")
            self._chat.configure(state="disabled")
            self._chat.see("end")

    def _dm_shortcut(self, username: str):
        self._entry.delete(0, "end")
        self._entry.insert(0, f"/dm {username} ")
        self._entry.focus()
        self._entry.icursor("end")

    # ── File operations ───────────────────────────────────────────────────────

    def _upload_file(self):
        if not self._connected:
            return
        path = filedialog.askopenfilename(parent=self, title="Select file to upload")
        if not path:
            return
        fname = os.path.basename(path)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            messagebox.showerror("Upload Error", str(e), parent=self)
            return
        try:
            _send(self._sock, {"type": "file_upload",
                               "filename": fname, "filesize": len(data)}, data)
        except OSError:
            self._on_disconnected()

    def _req_file_list(self):
        if not self._connected:
            return
        try:
            _send(self._sock, {"type": "get_files"})
        except OSError:
            pass

    def _download_file(self, filename: str):
        if not self._connected:
            return
        try:
            _send(self._sock, {"type": "file_download", "filename": filename})
        except OSError:
            self._on_disconnected()

    def _save_download(self, payload: dict, blob: bytes):
        fname = payload.get("filename", "downloaded_file")
        try:
            decrypted = decrypt_bytes(self.cipher, blob)
        except Exception as e:
            messagebox.showerror("Decrypt Error", f"Could not decrypt {fname}:\n{e}", parent=self)
            return
        save_path = filedialog.asksaveasfilename(
            parent=self, initialfile=fname,
            title="Save downloaded file",
            defaultextension=os.path.splitext(fname)[1] or "")
        if not save_path:
            return
        try:
            with open(save_path, "wb") as f:
                f.write(decrypted)
            self._chat.configure(state="normal")
            self._chat.insert("end", f"✔ Saved {fname} → {save_path}\n", "help")
            self._chat.configure(state="disabled")
            self._chat.see("end")
        except OSError as e:
            messagebox.showerror("Save Error", str(e), parent=self)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self.destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n} GB"


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="NetChat Client")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=cfg.PORT)
    args = ap.parse_args()

    login = LoginWindow(args.host, args.port)
    login.mainloop()
    if not login.result:
        return

    username, host, port = login.result
    app = ChatApp(username, host, port)
    app.mainloop()


if __name__ == "__main__":
    main()
