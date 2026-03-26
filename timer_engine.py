from audio_engine import AudioEngine

# ── Event definitions ────────────────────────────────────────────

EVENTS = [
    {"name": "power_rune",  "label": "Power Rune",  "interval": 120, "start": 0},
    {"name": "bounty_rune", "label": "Bounty Rune", "interval": 180, "start": 0},
    {"name": "lotus_pool",  "label": "Lotus Pool",  "interval": 180, "start": 180},
    {"name": "wisdom_rune", "label": "Wisdom Rune", "interval": 420, "start": 420},
    {"name": "neutrals",    "label": "Neutrals",     "interval": 60,  "start": 60},
]

IN_PROGRESS = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"

TICK_MS = 200  # timer resolution


class TimerEngine:
    def __init__(self, root, game_state, audio: AudioEngine, get_delays,
                 get_enabled=None, get_stop_at=None) -> None:
        """
        root:         tk.Tk (for root.after scheduling)
        game_state:   gsi_server.GameState
        audio:        AudioEngine instance
        get_delays:   callable returning dict[str, list[int]] of pre-alert offsets
        get_enabled:  callable returning set[str] of enabled event names (None = all)
        get_stop_at:  callable returning int|None — stop alerts after this many seconds
        """
        self._root = root
        self._game_state = game_state
        self._audio = audio
        self._get_delays = get_delays
        self._get_enabled = get_enabled
        self._get_stop_at = get_stop_at
        self._announced: set[str] = set()
        self._last_game_state: str = ""
        self._running = False
        self._after_id = None
        self._on_status_change = None
        self._schedule_built = False

    def set_status_callback(self, callback) -> None:
        """callback(status: str) where status is 'inactive', 'waiting', or 'active'."""
        self._on_status_change = callback

    def _notify_status(self, status: str) -> None:
        if self._on_status_change:
            self._on_status_change(status)

    def start(self) -> None:
        self._running = True
        self._announced.clear()
        self._schedule_built = False
        self._last_game_state = ""
        self._notify_status("waiting")
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            self._root.after_cancel(self._after_id)
            self._after_id = None
        self._audio.clear_schedule()
        self._schedule_built = False
        self._notify_status("inactive")

    def _build_schedule(self) -> None:
        """Build the full playback schedule from current config."""
        enabled = self._get_enabled() if self._get_enabled else {e["name"] for e in EVENTS}
        delays = self._get_delays()
        stop_at = self._get_stop_at() if self._get_stop_at else None
        horizon = stop_at if stop_at else 90 * 60
        self._audio.build_schedule(EVENTS, enabled, delays, horizon_seconds=horizon)
        self._schedule_built = True

    def _tick(self) -> None:
        if not self._running:
            return

        snap = self._game_state.snapshot()
        gs = snap["game_state"]

        # Detect match reset (state changed away from in-progress)
        if self._last_game_state == IN_PROGRESS and gs != IN_PROGRESS:
            self._announced.clear()
            self._audio.clear_schedule()
            self._schedule_built = False
            self._notify_status("waiting")
        self._last_game_state = gs

        if gs == IN_PROGRESS and not snap["paused"]:
            self._notify_status("active")
            clock = snap["clock_time"]

            # Build schedule on first active tick
            if not self._schedule_built:
                self._build_schedule()

            # Check a small window around the current clock to avoid missing
            for check_sec in range(int(clock) - 1, int(clock) + 2):
                key = f"@{check_sec}"
                if key not in self._announced:
                    clip = self._audio.get_clip_for_second(check_sec)
                    if clip is not None:
                        self._audio.play_wav(clip)
                        self._announced.add(key)
        elif gs == IN_PROGRESS and snap["paused"]:
            pass  # keep status as-is during pause
        else:
            if gs:
                self._notify_status("waiting")

        self._after_id = self._root.after(TICK_MS, self._tick)
