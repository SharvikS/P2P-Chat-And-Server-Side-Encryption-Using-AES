#!/usr/bin/env python3
"""
Generate README screenshots + animated GIFs by rendering the real UI
with demo data. Run: python generate_assets.py
"""

import os, time, sys
os.makedirs("assets", exist_ok=True)

# Force UTF-8 output so unicode print chars work on Windows
if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import ImageGrab, Image
import customtkinter as ctk
import tkinter as tk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG="#1a1b26"; BG2="#24283b"; BG3="#16161e"; BORD="#3b4261"
FG="#c0caf5"; DIM="#565f89"; BLUE="#7aa2f7"; CYAN="#7dcfff"
GRN="#9ece6a"; YLW="#e0af68"; RED="#f7768e"; MAG="#bb9af7"
USER_COLORS=[BLUE, CYAN, GRN, YLW, "#ff9e64", MAG, RED]
_cm={}

def uc(n):
    if n not in _cm: _cm[n]=USER_COLORS[len(_cm)%7]
    return _cm[n]

def grab(win):
    win.lift()
    win.attributes("-topmost", True)
    win.update()
    win.update_idletasks()
    time.sleep(0.2)
    # Account for Windows DPI scaling
    try:
        scale = win.winfo_fpixels("1i") / 96.0
    except Exception:
        scale = 1.0
    x = int(win.winfo_rootx() * scale)
    y = int(win.winfo_rooty() * scale)
    w = int(win.winfo_width()  * scale)
    h = int(win.winfo_height() * scale)
    return ImageGrab.grab((x, y, x+w, y+h), all_screens=True)

def save_gif(frames, path, dur=600):
    rgb = [f.convert("RGB") for f in frames]
    rgb[0].save(path, save_all=True, append_images=rgb[1:], duration=dur, loop=0)
    print(f"  [DONE] {path}  ({len(frames)} frames)")

# ── Demo data ─────────────────────────────────────────────────────────────────
USERS = ["Alice", "Bob", "Sharvik"]
FILES = ["project_report.pdf", "screenshot.png", "notes.txt"]
MSGS  = [
    {"type":"system","content":"NetChat v2.0  |  AES-128 Encrypted","timestamp":""},
    {"type":"system","content":"Alice joined the chat","timestamp":"14:30"},
    {"type":"chat","sender":"Alice","content":"Hey everyone! Testing NetChat v2.0","timestamp":"14:31"},
    {"type":"chat","sender":"Bob","content":"Dark theme looks amazing -- love the typing indicators","timestamp":"14:31"},
    {"type":"chat","sender":"Sharvik","content":"Uploading the project report -- gets AES-encrypted on the server","timestamp":"14:32"},
    {"type":"file_notification","filename":"project_report.pdf","sender":"Sharvik","filesize":43264,"timestamp":"14:32"},
    {"type":"dm","sender":"Bob","content":"Nice encryption impl! DMs work great too","timestamp":"14:33"},
    {"type":"chat","sender":"Alice","content":"Downloaded and decrypted the file in one click","timestamp":"14:33"},
]

# ── Single Tk root — all windows are CTkToplevel ──────────────────────────────
root = ctk.CTk()
root.withdraw()  # hide the root, all content is in Toplevel windows

# ── Login window ──────────────────────────────────────────────────────────────
class DemoLogin(ctk.CTkToplevel):
    def __init__(self):
        super().__init__(root)
        self.title("NetChat -- Connect")
        self.geometry("400x340")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        ctk.CTkLabel(self, text="NetChat",
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=BLUE).pack(pady=(36,2))
        ctk.CTkLabel(self, text="AES-Encrypted P2P Chat",
                     font=ctk.CTkFont(size=12), text_color=DIM).pack(pady=(0,28))

        fr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=12)
        fr.pack(fill="x", padx=32, pady=4)
        fr.columnconfigure(0, weight=1)

        def row(lbl, val, r):
            ctk.CTkLabel(fr, text=lbl, text_color=DIM,
                         font=ctk.CTkFont(size=11)).grid(
                         row=r, column=0, sticky="w", padx=16, pady=(12,0))
            e = ctk.CTkEntry(fr, fg_color=BG3, border_color=BORD,
                             text_color=FG, height=36, corner_radius=8)
            e.insert(0, val)
            e.grid(row=r+1, column=0, sticky="ew", padx=16, pady=(2,12))
            return e

        self.name_e = row("Username", "", 0)
        row("Server Host", "192.168.1.10", 2)
        row("Port", "65432", 4)

        ctk.CTkButton(self, text="Connect", height=42, corner_radius=10,
                      fg_color=BLUE, hover_color="#5d8ef0", text_color=BG,
                      font=ctk.CTkFont(size=14, weight="bold")).pack(
                      fill="x", padx=32, pady=16)
        ctk.CTkLabel(self, text="", text_color=RED,
                     font=ctk.CTkFont(size=11)).pack()

# ── Chat window ───────────────────────────────────────────────────────────────
class DemoChat(ctk.CTkToplevel):
    def __init__(self):
        super().__init__(root)
        self.title("NetChat  --  Sharvik")
        self.geometry("1000x660")
        self.configure(fg_color=BG)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG2, height=48, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="●", text_color=GRN,
                     font=ctk.CTkFont(size=14)).pack(side="left", padx=(16,4))
        ctk.CTkLabel(hdr, text="NetChat",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=FG).pack(side="left")
        ctk.CTkLabel(hdr, text="Connected as Sharvik",
                     font=ctk.CTkFont(size=11), text_color=DIM).pack(
                     side="left", padx=10)
        ctk.CTkLabel(hdr, text="  AES-128",
                     font=ctk.CTkFont(size=10), text_color=DIM).pack(
                     side="right", padx=16)
        ctk.CTkLabel(hdr, text="192.168.1.10:65432",
                     font=ctk.CTkFont(size=10), text_color=DIM).pack(
                     side="right", padx=(0,8))

        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1); body.rowconfigure(0, weight=1)

        sb = ctk.CTkFrame(body, fg_color=BG2, width=190, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew"); sb.pack_propagate(False)
        ctk.CTkLabel(sb, text="ONLINE",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=DIM).pack(anchor="w", padx=14, pady=(14,4))
        self._uf = ctk.CTkScrollableFrame(sb, fg_color=BG2,
                                           scrollbar_button_color=BG3, height=200)
        self._uf.pack(fill="x", padx=6)
        ctk.CTkFrame(sb, fg_color=BORD, height=1,
                     corner_radius=0).pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(sb, text="SERVER FILES",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=DIM).pack(anchor="w", padx=14, pady=(0,4))
        self._ff = ctk.CTkScrollableFrame(sb, fg_color=BG2,
                                           scrollbar_button_color=BG3)
        self._ff.pack(fill="both", expand=True, padx=6, pady=(0,6))
        ctk.CTkButton(sb, text="Refresh Files", height=30, fg_color=BG3,
                      hover_color=BORD, text_color=DIM,
                      font=ctk.CTkFont(size=11), corner_radius=6).pack(
                      fill="x", padx=10, pady=(0,10))

        cc = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        cc.grid(row=0, column=1, sticky="nsew")
        cc.rowconfigure(0, weight=1); cc.columnconfigure(0, weight=1)

        tf = ctk.CTkFrame(cc, fg_color=BG3, corner_radius=0)
        tf.grid(row=0, column=0, sticky="nsew")
        tf.rowconfigure(0, weight=1); tf.columnconfigure(0, weight=1)

        self._chat = tk.Text(tf, state="disabled", wrap="word", cursor="arrow",
                             bg=BG3, fg=FG, font=("Segoe UI", 11), bd=0,
                             relief="flat", padx=14, pady=10, spacing1=2, spacing3=6)
        self._chat.grid(row=0, column=0, sticky="nsew")
        sx = tk.Scrollbar(tf, command=self._chat.yview, bg=BG3,
                          troughcolor=BG3, bd=0, relief="flat", width=8)
        sx.grid(row=0, column=1, sticky="ns")
        self._chat.configure(yscrollcommand=sx.set)
        self._def_tags()

        self._tl = ctk.CTkLabel(cc, text="", text_color=DIM,
                                 font=ctk.CTkFont(size=10, slant="italic"),
                                 height=16, anchor="w")
        self._tl.grid(row=1, column=0, sticky="ew", padx=14)

        inp = ctk.CTkFrame(cc, fg_color=BG2, height=60, corner_radius=0)
        inp.grid(row=2, column=0, sticky="ew")
        inp.pack_propagate(False); inp.columnconfigure(1, weight=1)
        ctk.CTkButton(inp, text="Upload", width=56, height=36, fg_color=BG3,
                      hover_color=BORD, text_color=YLW, corner_radius=8,
                      font=ctk.CTkFont(size=11)).grid(
                      row=0, column=0, padx=(10,4), pady=12)
        self._ent = ctk.CTkEntry(inp,
                      placeholder_text="Message...  or /help for commands",
                      fg_color=BG3, border_color=BORD, text_color=FG,
                      placeholder_text_color=DIM, height=36, corner_radius=8,
                      font=ctk.CTkFont(size=12))
        self._ent.grid(row=0, column=1, sticky="ew", padx=4, pady=12)
        ctk.CTkButton(inp, text="Send", width=72, height=36, fg_color=BLUE,
                      hover_color="#5d8ef0", text_color=BG,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      corner_radius=8).grid(
                      row=0, column=2, padx=(4,10), pady=12)

    def _def_tags(self):
        t = self._chat
        t.tag_configure("system",    foreground=DIM, font=("Segoe UI",10,"italic"),
                         justify="center", spacing1=4, spacing3=4)
        t.tag_configure("timestamp", foreground=DIM, font=("Segoe UI",9))
        t.tag_configure("self_name", foreground=CYAN, font=("Segoe UI",11,"bold"))
        t.tag_configure("self_msg",  foreground=FG)
        t.tag_configure("dm_name",   foreground=MAG, font=("Segoe UI",11,"bold"))
        t.tag_configure("dm_msg",    foreground=MAG)
        t.tag_configure("file_note", foreground=YLW, font=("Segoe UI",10))

    def _utag(self, name):
        tag = f"u_{name}"
        if tag not in self._chat.tag_names():
            self._chat.tag_configure(tag, foreground=uc(name),
                                     font=("Segoe UI",11,"bold"))
        return tag

    def add_user(self, name):
        is_you = (name == "Sharvik")
        ctk.CTkButton(self._uf,
                      text=f"  {name}{'  (you)' if is_you else ''}",
                      anchor="w", fg_color="transparent", hover_color=BG3,
                      text_color=CYAN if is_you else uc(name),
                      font=ctk.CTkFont(size=12), height=28,
                      corner_radius=6).pack(fill="x", pady=1)

    def add_file(self, fname):
        ctk.CTkButton(self._ff, text=f"  {fname}", anchor="w",
                      fg_color="transparent", hover_color=BG3,
                      text_color=YLW, font=ctk.CTkFont(size=11),
                      height=26, corner_radius=6).pack(fill="x", pady=1)

    def render(self, msg):
        t = msg.get("type"); ts = msg.get("timestamp","")
        c = self._chat; c.configure(state="normal")
        if t == "system":
            c.insert("end", f"\n-- {msg['content']} --\n", "system")
        elif t == "chat":
            s = msg["sender"]
            tag = "self_name" if s == "Sharvik" else self._utag(s)
            c.insert("end", s, tag)
            c.insert("end", f"  {ts}\n", "timestamp")
            c.insert("end", f"{msg['content']}\n\n", "self_msg")
        elif t == "dm":
            c.insert("end", f"[DM] {msg['sender']}", "dm_name")
            c.insert("end", f"  {ts}\n", "timestamp")
            c.insert("end", f"{msg['content']}\n\n", "dm_msg")
        elif t == "file_notification":
            sz = msg["filesize"]
            for u, s in ((1<<20,"MB"),(1<<10,"KB")):
                if sz >= u: szs = f"{sz/u:.1f} {s}"; break
            else: szs = f"{sz} B"
            c.insert("end",
                f"[FILE] {msg['sender']} shared '{msg['filename']}'"
                f" ({szs}) -- click to download\n\n", "file_note")
        c.configure(state="disabled"); c.see("end")

    def set_entry(self, text):
        self._ent.delete(0,"end"); self._ent.insert(0, text)

    def set_typing(self, text):
        self._tl.configure(text=text)

# ── Orchestrator (runs inside single mainloop) ────────────────────────────────
def run_all():
    print("  [1/2] Login window...")

    login = DemoLogin()
    login.update(); login.update_idletasks()

    def do_login():
        try:
            # Static screenshot with username filled in
            login.name_e.insert(0, "Sharvik")
            login.update()
            img = grab(login)
            img.save("assets/login.png")
            print("  [DONE] assets/login.png")

            # Typing GIF: empty -> S -> Sh -> ... -> Sharvik
            login.name_e.delete(0,"end"); login.update()
            frames = [grab(login), grab(login)]  # hold empty state
            for ch in "Sharvik":
                login.name_e.insert("end", ch); login.update()
                time.sleep(0.04)
                frames.append(grab(login))
            for _ in range(5): frames.append(frames[-1])
            save_gif(frames, "assets/login_demo.gif", dur=190)

        except Exception as e:
            print(f"  [ERROR] login: {e}")
        finally:
            login.destroy()
            root.after(200, do_chat)

    def do_chat():
        print("  [2/2] Chat window...")
        chat = DemoChat()
        chat.update(); chat.update_idletasks()

        def run_chat():
            try:
                frames = []
                for u in USERS: chat.add_user(u)
                for f in FILES: chat.add_file(f)
                chat.update()
                frames.append(grab(chat))  # initial empty state

                for msg in MSGS:
                    chat.render(msg); chat.update()
                    frames.append(grab(chat))
                    frames.append(grab(chat))  # hold 2 frames per message

                # Typing indicator
                chat.set_typing("Alice is typing..."); chat.update()
                for _ in range(4): frames.append(grab(chat))

                # Final reply
                chat.set_typing("")
                chat.render({"type":"chat","sender":"Alice",
                             "content":"Encryption is seamless! Love this app",
                             "timestamp":"14:34"})
                chat.set_entry("Thanks! Glad it works well")
                chat.update()
                for _ in range(4): frames.append(grab(chat))

                frames[-1].save("assets/chat.png")
                print("  [DONE] assets/chat.png")
                save_gif(frames, "assets/demo.gif", dur=580)

            except Exception as e:
                print(f"  [ERROR] chat: {e}")
                import traceback; traceback.print_exc()
            finally:
                chat.destroy()
                root.after(200, root.destroy)

        chat.after(400, run_chat)

    login.after(450, do_login)

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  NetChat - generating README assets")
    print("-" * 42)
    root.after(100, run_all)
    root.mainloop()
    print("\n  Done! Check assets/")
    print("-" * 42)
