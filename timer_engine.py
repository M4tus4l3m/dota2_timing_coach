from audio_engine import AudioEngine, get_closest_delay

# ── Event definitions ────────────────────────────────────────────

EVENTS = [
    {"name": "power_rune",  "label": "Power Rune",  "interval": 120, "start": 0},
    {"name": "bounty_rune", "label": "Bounty Rune", "interval": 180, "start": 0},
    {"name": "lotus_pool",  "label": "Lotus Pool",  "interval": 180, "start": 0},
    {"name": "wisdom_rune", "label": "Wisdom Rune", "interval": 420, "start": 0},
    {"name": "stack",       "label": "Stack",        "interval": 60,  "start": 60},
]

IN_PROGRESS = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"

TICK_MS = 200  # timer resolution


class TimerEngine:
    def __init__(self, root, game_state, audio: AudioEngine, get_delays) -> None:
        """
        root:       tk.Tk (for root.after scheduling)
        game_state: gsi_server.GameState
        audio:      AudioEngine instance
        get_delays: callable returning dict[str, int] of pre-alert offsets
        """
        self._root = root
        self._game_state = game_state
        self._audio = audio
        self._get_delays = get_delays
        self._announced: set[str] = set()
        self._last_game_state: str = ""
        self._running = False
        self._after_id = None
        self._on_status_change = None

    def set_status_callback(self, callback) -> None:
        """callback(status: str) where status is 'inactive', 'waiting', or 'active'."""
        self._on_status_change = callback

    def _notify_status(self, status: str) -> None:
        if self._on_status_change:
            self._on_status_change(status)

    def start(self) -> None:
        self._running = True
        self._announced.clear()
        self._last_game_state = ""
        self._notify_status("waiting")
        self._tick()

    def stop(self) -> None:
        self._running = False
        if self._after_id is not None:
            self._root.after_cancel(self._after_id)
            self._after_id = None
        self._notify_status("inactive")

    def _tick(self) -> None:
        if not self._running:
            return

        snap = self._game_state.snapshot()
        gs = snap["game_state"]

        # Detect match reset (state changed away from in-progress)
        if self._last_game_state == IN_PROGRESS and gs != IN_PROGRESS:
            self._announced.clear()
            self._notify_status("waiting")
        self._last_game_state = gs

        if gs == IN_PROGRESS and not snap["paused"]:
            self._notify_status("active")
            clock = snap["clock_time"]
            delays = self._get_delays()
            for event in EVENTS:
                self._check_event(event, clock, delays.get(event["name"], 30))
        elif gs == IN_PROGRESS and snap["paused"]:
            pass  # keep status as-is during pause
        else:
            if gs:
                self._notify_status("waiting")

        self._after_id = self._root.after(TICK_MS, self._tick)

    def _check_event(self, event: dict, clock: float, pre_delay: int) -> None:
        name = event["name"]
        interval = event["interval"]
        start = event["start"]

        # Generate occurrence times within a reasonable window
        # Check occurrences from start up to clock + max possible pre-delay + buffer
        max_check = clock + 65  # slightly beyond max delay (60) + tick margin

        t = start
        while t <= max_check:
            # On-time alert
            on_key = f"{name}@{t}"
            if on_key not in self._announced:
                if t >= 0 and abs(clock - t) < 1.5:
                    self._audio.play(name)
                    self._announced.add(on_key)

            # Pre-alert
            if pre_delay > 0:
                pre_time = t - pre_delay
                pre_key = f"{name}_pre@{t}"
                if pre_key not in self._announced:
                    if pre_time >= 0 and abs(clock - pre_time) < 1.5:
                        snapped = get_closest_delay(pre_delay)
                        clip_name = f"{name}_pre_{snapped}"
                        self._audio.play(clip_name)
                        self._announced.add(pre_key)

            t += interval
