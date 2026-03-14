import json
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from audio_engine import AudioEngine
from gsi_server import GameState, GSIServer
from timer_engine import TimerEngine, EVENTS


# ── Dark Dota 2 theme ───────────────────────────────────────────

TH = {
    "bg":        "#1e1e2e",   # main background
    "bg_frame":  "#252535",   # panel / label-frame background
    "bg_entry":  "#333345",   # entry fields
    "bg_btn":    "#4CAF50",   # green button
    "bg_btn_act": "#388E3C",  # button pressed
    "bg_btn_stop": "#c0392b", # red stop button
    "bg_btn_stop_act": "#962d22",
    "fg":        "#c8c8d0",   # main text
    "fg_header": "#88a088",   # table headers (muted green-grey)
    "fg_btn":    "#ffffff",   # button text
    "fg_entry":  "#e0e0e8",   # entry text
    "border":    "#3a3a4a",   # subtle borders
    "green":     "#4CAF50",
    "insert":    "#c8c8d0",   # entry cursor color
}

STATUS_COLORS = {
    "inactive": "#888888",
    "waiting":  "#e8a000",
    "active":   "#00b050",
}

STATUS_LABELS = {
    "inactive": "Inactive",
    "waiting":  "Waiting for Dota 2",
    "active":   "Active",
}

DEFAULT_PRE_ALERT = 30

DEFAULT_STEAM_PATH = r"C:\Program Files (x86)\Steam"

ICON_MAP = {
    "power_rune":  "power.png",
    "bounty_rune": "bounty.png",
    "lotus_pool":  "lotus.png",
    "wisdom_rune": "wisdom.png",
    "neutrals":    "ancient.png",
}

ICON_SIZE = (20, 20)
MAX_OFFSETS = 3

FONT_MAIN = ("Segoe UI", 10)
FONT_HEADER = ("Segoe UI", 9, "bold")
FONT_BTN = ("Segoe UI", 10, "bold")

_IS_WINDOWS = sys.platform == "win32"


def _asset_path(filename: str) -> str:
    """Resolve asset path for both dev and PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", filename)


def _config_path() -> str:
    """Config file lives next to the executable (or script directory)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")


def _load_config() -> dict:
    path = _config_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_config(cfg: dict) -> None:
    try:
        with open(_config_path(), "w") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def _themed_label(parent, text="", font=FONT_MAIN, fg=None, bg=None, **kw):
    return tk.Label(
        parent, text=text, font=font,
        fg=fg or TH["fg"], bg=bg or TH["bg_frame"], **kw,
    )


def _themed_entry(parent, width=6, **kw):
    return tk.Entry(
        parent, width=width, justify="center", font=FONT_MAIN,
        bg=TH["bg_entry"], fg=TH["fg_entry"],
        insertbackground=TH["insert"],
        relief="flat", highlightthickness=1,
        highlightbackground=TH["border"], highlightcolor=TH["green"],
        **kw,
    )


def _rounded_rect(canvas, x1, y1, x2, y2, r=5, **kwargs):
    """Draw a rounded rectangle on a canvas using a smooth polygon."""
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class App:
    def __init__(self, root: tk.Tk, audio: AudioEngine) -> None:
        self._root = root
        self._audio = audio
        self._root.title("Dota 2 Timer Assistant")
        self._root.resizable(False, False)
        self._root.configure(bg=TH["bg"])

        # Set window icon (shows in OS title bar + taskbar)
        try:
            img = Image.open(_asset_path("dota.png"))
            self._icon_img = ImageTk.PhotoImage(img)
            self._root.iconphoto(True, self._icon_img)
        except (OSError, tk.TclError):
            pass

        self._game_state = GameState()
        self._gsi_server = GSIServer(self._game_state)

        self._running = False
        self._offset_data: dict[str, dict] = {}
        self._enabled_vars: dict[str, tk.BooleanVar] = {}
        self._icon_refs: list[ImageTk.PhotoImage] = []  # prevent GC

        self._config = _load_config()

        self._build_ui()
        self._apply_config()

        # Windows: replace OS frame with custom title bar
        if _IS_WINDOWS:
            self._root.update_idletasks()
            self._root.overrideredirect(True)
            self._center_window()

        self._timer_engine = TimerEngine(
            root, self._game_state, audio,
            self.get_pre_alert_delays, self.get_enabled_events
        )
        self._timer_engine.set_status_callback(self._update_status)

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Custom title bar (Windows only — on Linux/WSL the OS frame is used)
        if _IS_WINDOWS:
            self._build_title_bar()

        # Steam folder row
        frm_steam = tk.Frame(self._root, padx=10, pady=8, bg=TH["bg"])
        frm_steam.pack(fill="x")

        tk.Label(
            frm_steam, text="Steam folder:", font=FONT_MAIN,
            fg=TH["fg"], bg=TH["bg"],
        ).pack(side="left")

        self._steam_entry = tk.Entry(
            frm_steam, width=40, font=FONT_MAIN,
            bg=TH["bg_entry"], fg=TH["fg_entry"],
            insertbackground=TH["insert"],
            relief="flat", highlightthickness=1,
            highlightbackground=TH["border"], highlightcolor=TH["green"],
        )
        self._steam_entry.pack(side="left", padx=5)

        tk.Button(
            frm_steam, text="Browse...", font=FONT_MAIN,
            bg=TH["bg_frame"], fg=TH["fg"], activebackground=TH["border"],
            activeforeground=TH["fg"], relief="flat", padx=8, cursor="hand2",
        ).pack(side="left")
        # re-bind command (button created inline)
        frm_steam.winfo_children()[-1].config(command=self._browse_steam)

        # Event table
        frm_table = tk.LabelFrame(
            self._root, text="  Event Timers  ", padx=10, pady=8,
            font=FONT_HEADER, fg=TH["fg_header"], bg=TH["bg_frame"],
            bd=1, relief="groove",
        )
        frm_table.pack(fill="x", padx=10, pady=5)

        headers = ["", "", "Event", "Interval", "Offset"]
        for col, header in enumerate(headers):
            tk.Label(
                frm_table, text=header, font=FONT_HEADER,
                fg=TH["fg_header"], bg=TH["bg_frame"],
            ).grid(row=0, column=col, padx=5, pady=4, sticky="w")

        for row, event in enumerate(EVENTS, start=1):
            # Column 0: Checkbox
            var = tk.BooleanVar(value=True)
            self._enabled_vars[event["name"]] = var
            tk.Checkbutton(
                frm_table, variable=var,
                bg=TH["bg_frame"], activebackground=TH["bg_frame"],
                selectcolor="#ffffff", highlightthickness=0,
            ).grid(row=row, column=0, padx=2, pady=3)

            # Column 1: Icon
            icon_file = ICON_MAP.get(event["name"])
            if icon_file:
                try:
                    img = Image.open(_asset_path(icon_file))
                    img = img.resize(ICON_SIZE, Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._icon_refs.append(photo)
                    tk.Label(
                        frm_table, image=photo, bg=TH["bg_frame"],
                    ).grid(row=row, column=1, padx=2, pady=3)
                except (OSError, tk.TclError):
                    _themed_label(frm_table).grid(row=row, column=1)
            else:
                _themed_label(frm_table).grid(row=row, column=1)

            # Column 2: Event name
            _themed_label(frm_table, text=event["label"]).grid(
                row=row, column=2, padx=5, pady=3, sticky="w"
            )

            # Column 3: Interval
            _themed_label(frm_table, text=f'{event["interval"]}s').grid(
                row=row, column=3, padx=5, pady=3, sticky="w"
            )

            # Column 4: Offset container (multi-offset with add/remove)
            container = tk.Frame(frm_table, bg=TH["bg_frame"])
            container.grid(row=row, column=4, padx=5, pady=3, sticky="w")

            first_entry = _themed_entry(container, width=6)
            first_entry.insert(0, str(DEFAULT_PRE_ALERT))
            first_entry.pack(side="left")

            # "+" button: green rounded-rect on canvas
            add_canvas = tk.Canvas(
                container, width=22, height=22,
                highlightthickness=0, bg=TH["bg_frame"], cursor="hand2",
            )
            _rounded_rect(add_canvas, 2, 2, 20, 20, r=5,
                          fill=TH["green"], outline="")
            add_canvas.create_text(11, 11, text="+", fill="#ffffff",
                                   font=("Segoe UI", 11, "bold"))
            add_canvas.pack(side="left", padx=(4, 0))

            event_name = event["name"]
            add_canvas.bind("<Button-1>",
                            lambda e, n=event_name: self._add_offset(n))

            self._offset_data[event_name] = {
                "container": container,
                "entries": [first_entry],
                "remove_btns": [],
                "add_btn": add_canvas,
            }

        # Controls row
        frm_ctrl = tk.Frame(self._root, padx=10, pady=8, bg=TH["bg"])
        frm_ctrl.pack(fill="x")

        self._toggle_btn = tk.Button(
            frm_ctrl, text="START", width=12, font=FONT_BTN,
            bg=TH["bg_btn"], fg=TH["fg_btn"],
            activebackground=TH["bg_btn_act"], activeforeground=TH["fg_btn"],
            relief="flat", cursor="hand2", padx=10, pady=4,
        )
        self._toggle_btn.config(command=self._toggle)
        self._toggle_btn.pack(side="left")

        # Status indicator
        frm_status = tk.Frame(frm_ctrl, bg=TH["bg"])
        frm_status.pack(side="right")

        self._status_dot = tk.Canvas(
            frm_status, width=14, height=14,
            highlightthickness=0, bg=TH["bg"],
        )
        self._status_dot.pack(side="left", padx=4)
        self._dot_id = self._status_dot.create_oval(
            2, 2, 12, 12, fill="#888888", outline=""
        )

        self._status_label = tk.Label(
            frm_status, text="Inactive", font=FONT_MAIN,
            fg=TH["fg"], bg=TH["bg"],
        )
        self._status_label.pack(side="left")

    def _build_title_bar(self) -> None:
        """Custom title bar with icon, title, minimize and close (Windows)."""
        title_bar = tk.Frame(self._root, bg=TH["bg"])
        title_bar.pack(fill="x")

        # Icon
        icon_label = tk.Label(title_bar, bg=TH["bg"])
        try:
            img = Image.open(_asset_path("dota.png"))
            img = img.resize((20, 20), Image.LANCZOS)
            self._title_icon = ImageTk.PhotoImage(img)
            icon_label.config(image=self._title_icon)
        except (OSError, tk.TclError):
            pass
        icon_label.pack(side="left", padx=(8, 4), pady=4)

        # Title text (expands to fill space)
        title_label = tk.Label(
            title_bar, text="Dota 2 Timer Assistant", font=FONT_MAIN,
            fg=TH["fg"], bg=TH["bg"], anchor="w",
        )
        title_label.pack(side="left", fill="x", expand=True, pady=4)

        # Close button
        close_btn = tk.Button(
            title_bar, text="\u2715", font=FONT_MAIN, width=3,
            bg=TH["bg"], fg="#e06060", relief="flat", bd=0,
            highlightthickness=0,
            activebackground="#c0392b", activeforeground="#ffffff",
            command=self._on_close, cursor="hand2",
        )
        close_btn.pack(side="right", pady=2, padx=(0, 4))

        # Minimize button
        minimize_btn = tk.Button(
            title_bar, text="\u2014", font=FONT_MAIN, width=3,
            bg=TH["bg"], fg=TH["fg"], relief="flat", bd=0,
            highlightthickness=0,
            activebackground=TH["border"], activeforeground=TH["fg"],
            command=self._minimize, cursor="hand2",
        )
        minimize_btn.pack(side="right", pady=2)

        # Drag-to-move bindings
        for widget in (title_bar, icon_label, title_label):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

    # ── Multi-offset add / remove ────────────────────────────────────

    def _add_offset(self, event_name: str,
                    value: int = DEFAULT_PRE_ALERT) -> None:
        data = self._offset_data[event_name]
        if len(data["entries"]) >= MAX_OFFSETS:
            return

        # Temporarily remove "+" so new widgets pack before it
        data["add_btn"].pack_forget()

        entry = _themed_entry(data["container"], width=6)
        entry.insert(0, str(value))
        entry.pack(side="left", padx=(4, 0))

        remove_btn = tk.Button(
            data["container"], text="x", font=("Segoe UI", 8),
            bg=TH["bg_frame"], fg=TH["fg"], activebackground=TH["border"],
            activeforeground=TH["fg"], relief="flat", padx=2, pady=0,
            cursor="hand2",
        )
        remove_btn.pack(side="left")

        data["entries"].append(entry)
        data["remove_btns"].append(remove_btn)

        remove_btn.config(
            command=lambda n=event_name, e=entry, b=remove_btn:
                self._remove_offset(n, e, b)
        )

        # Show "+" again if still under max
        if len(data["entries"]) < MAX_OFFSETS:
            data["add_btn"].pack(side="left", padx=(4, 0))

    def _remove_offset(self, event_name: str,
                       entry: tk.Entry, btn: tk.Button) -> None:
        data = self._offset_data[event_name]
        entry.destroy()
        btn.destroy()
        data["entries"].remove(entry)
        data["remove_btns"].remove(btn)

        if len(data["entries"]) < MAX_OFFSETS:
            data["add_btn"].pack_forget()
            data["add_btn"].pack(side="left", padx=(4, 0))

    # ── Config persistence ────────────────────────────────────────────

    def _apply_config(self) -> None:
        """Apply saved config to UI widgets."""
        steam = self._config.get("steam_path", DEFAULT_STEAM_PATH)
        self._steam_entry.delete(0, tk.END)
        self._steam_entry.insert(0, steam)

        enabled = self._config.get("enabled", {})
        for name, var in self._enabled_vars.items():
            if name in enabled:
                var.set(enabled[name])

        offsets = self._config.get("offsets", {})
        for name, data in self._offset_data.items():
            if name in offsets:
                raw = offsets[name]
                # Backward compat: single int → list
                values = [raw] if isinstance(raw, int) else raw
                if values:
                    data["entries"][0].delete(0, tk.END)
                    data["entries"][0].insert(0, str(values[0]))
                    for v in values[1:]:
                        self._add_offset(name, value=v)

    def _gather_config(self) -> dict:
        """Gather current UI state into a config dict."""
        return {
            "steam_path": self._steam_entry.get().strip(),
            "enabled": {name: var.get() for name, var in self._enabled_vars.items()},
            "offsets": self.get_pre_alert_delays(),
        }

    # ── Actions ──────────────────────────────────────────────────────

    def _browse_steam(self) -> None:
        path = filedialog.askdirectory(title="Select Steam installation folder")
        if path:
            self._steam_entry.delete(0, tk.END)
            self._steam_entry.insert(0, path)

    def _toggle(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        steam = self._steam_entry.get().strip()
        if not steam:
            messagebox.showerror("Error", "Please select your Steam folder.")
            return

        try:
            GSIServer.write_gsi_config(steam)
        except OSError as e:
            messagebox.showerror("Error", f"Failed to write GSI config:\n{e}")
            return

        try:
            self._gsi_server.start()
        except OSError as e:
            messagebox.showerror("Error", f"Failed to start GSI server:\n{e}")
            return

        self._timer_engine.start()
        self._running = True
        self._toggle_btn.config(
            text="STOP", bg=TH["bg_btn_stop"],
            activebackground=TH["bg_btn_stop_act"],
        )

    def _stop(self) -> None:
        self._timer_engine.stop()
        self._gsi_server.stop()
        self._running = False
        self._toggle_btn.config(
            text="START", bg=TH["bg_btn"],
            activebackground=TH["bg_btn_act"],
        )

    def _update_status(self, status: str) -> None:
        color = STATUS_COLORS.get(status, "#888888")
        label = STATUS_LABELS.get(status, "Unknown")
        self._status_dot.itemconfig(self._dot_id, fill=color)
        self._status_label.config(text=label)

    def get_pre_alert_delays(self) -> dict[str, list[int]]:
        """Read per-event pre-alert offsets from the UI table."""
        delays = {}
        for name, data in self._offset_data.items():
            values = []
            for entry in data["entries"]:
                try:
                    val = int(entry.get().strip())
                    values.append(max(0, val))
                except ValueError:
                    values.append(DEFAULT_PRE_ALERT)
            delays[name] = values
        return delays

    def get_enabled_events(self) -> set[str]:
        """Return the set of event names that are currently checked."""
        return {name for name, var in self._enabled_vars.items() if var.get()}

    # ── Window management (Windows custom frame) ─────────────────────

    def _center_window(self) -> None:
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    def _drag_start(self, event) -> None:
        self._drag_offset_x = event.x_root - self._root.winfo_x()
        self._drag_offset_y = event.y_root - self._root.winfo_y()

    def _drag_move(self, event) -> None:
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self._root.geometry(f"+{x}+{y}")

    def _minimize(self) -> None:
        self._root.overrideredirect(False)
        self._root.iconify()
        self._root.bind("<Map>", self._on_restore)

    def _on_restore(self, event) -> None:
        self._root.unbind("<Map>")
        self._root.overrideredirect(True)

    def _on_close(self) -> None:
        _save_config(self._gather_config())
        if self._running:
            self._stop()
        self._audio.shutdown()
        self._root.destroy()
