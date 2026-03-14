import tkinter as tk
from tkinter import filedialog, messagebox

from audio_engine import AudioEngine
from gsi_server import GameState, GSIServer
from timer_engine import TimerEngine, EVENTS


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


class App:
    def __init__(self, root: tk.Tk, audio: AudioEngine) -> None:
        self._root = root
        self._audio = audio
        self._root.title("Dota 2 Timer Assistant")
        self._root.resizable(False, False)

        self._game_state = GameState()
        self._gsi_server = GSIServer(self._game_state)
        self._timer_engine = TimerEngine(
            root, self._game_state, audio, self.get_pre_alert_delays
        )
        self._timer_engine.set_status_callback(self._update_status)
        self._running = False

        self._delay_entries: dict[str, tk.Entry] = {}

        self._build_ui()
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Steam folder row
        frm_steam = tk.Frame(self._root, padx=10, pady=5)
        frm_steam.pack(fill="x")

        tk.Label(frm_steam, text="Steam folder:").pack(side="left")
        self._steam_entry = tk.Entry(frm_steam, width=40)
        self._steam_entry.pack(side="left", padx=5)
        tk.Button(frm_steam, text="Browse...", command=self._browse_steam).pack(side="left")

        # Event table
        frm_table = tk.LabelFrame(self._root, text="Event Timers", padx=10, pady=5)
        frm_table.pack(fill="x", padx=10, pady=5)

        headers = ["Event", "Interval", "Start", "Pre-alert (s)"]
        for col, header in enumerate(headers):
            tk.Label(frm_table, text=header, font=("", 9, "bold")).grid(
                row=0, column=col, padx=5, pady=2, sticky="w"
            )

        for row, event in enumerate(EVENTS, start=1):
            tk.Label(frm_table, text=event["label"]).grid(
                row=row, column=0, padx=5, pady=2, sticky="w"
            )
            tk.Label(frm_table, text=f'{event["interval"]}s').grid(
                row=row, column=1, padx=5, pady=2, sticky="w"
            )
            tk.Label(frm_table, text=f'{event["start"]}s').grid(
                row=row, column=2, padx=5, pady=2, sticky="w"
            )
            entry = tk.Entry(frm_table, width=6, justify="center")
            entry.insert(0, str(DEFAULT_PRE_ALERT))
            entry.grid(row=row, column=3, padx=5, pady=2)
            self._delay_entries[event["name"]] = entry

        # Controls row
        frm_ctrl = tk.Frame(self._root, padx=10, pady=5)
        frm_ctrl.pack(fill="x")

        self._toggle_btn = tk.Button(
            frm_ctrl, text="Start", width=12, command=self._toggle
        )
        self._toggle_btn.pack(side="left")

        # Status indicator
        frm_status = tk.Frame(frm_ctrl)
        frm_status.pack(side="right")

        self._status_dot = tk.Canvas(frm_status, width=14, height=14, highlightthickness=0)
        self._status_dot.pack(side="left", padx=(0, 4))
        self._dot_id = self._status_dot.create_oval(2, 2, 12, 12, fill="#888888", outline="")

        self._status_label = tk.Label(frm_status, text="Inactive")
        self._status_label.pack(side="left")

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
        self._toggle_btn.config(text="Stop")

    def _stop(self) -> None:
        self._timer_engine.stop()
        self._gsi_server.stop()
        self._running = False
        self._toggle_btn.config(text="Start")

    def _update_status(self, status: str) -> None:
        color = STATUS_COLORS.get(status, "#888888")
        label = STATUS_LABELS.get(status, "Unknown")
        self._status_dot.itemconfig(self._dot_id, fill=color)
        self._status_label.config(text=label)

    def get_pre_alert_delays(self) -> dict[str, int]:
        """Read per-event pre-alert offsets from the UI table."""
        delays = {}
        for name, entry in self._delay_entries.items():
            try:
                val = int(entry.get().strip())
                delays[name] = max(0, val)
            except ValueError:
                delays[name] = DEFAULT_PRE_ALERT
        return delays

    def _on_close(self) -> None:
        if self._running:
            self._stop()
        self._audio.shutdown()
        self._root.destroy()
