import os
import queue
import shutil
import tempfile
import threading

import pyttsx3
import pygame


# Events that get TTS clips generated
EVENTS = ["power rune", "bounty rune", "lotus pool", "wisdom rune", "neutrals"]

# Supported pre-alert delay values (seconds)
SUPPORTED_DELAYS = [5, 10, 15, 20, 25, 30, 45, 60]

_SENTINEL = None


def get_closest_delay(requested: int) -> int:
    """Snap a requested delay to the nearest supported value."""
    if requested <= 0:
        return 0
    return min(SUPPORTED_DELAYS, key=lambda d: abs(d - requested))


def _clip_key(event: str) -> str:
    """Convert display name to file-safe key: 'power rune' -> 'power_rune'."""
    return event.replace(" ", "_")


class AudioEngine:
    def __init__(self) -> None:
        self._mixer_ok = False
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self._mixer_ok = True
        except pygame.error:
            pass
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._clip_dir = tempfile.mkdtemp(prefix="dota2timer_")
        self._clips: dict[str, str] = {}  # clip_name -> wav path
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    # ── TTS generation ──────────────────────────────────────────────

    def generate_clips(self, on_progress=None) -> None:
        """Pre-generate all TTS WAV clips. Call from main thread at startup."""
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)

        texts: dict[str, str] = {}

        # On-time clips: "power rune"
        for event in EVENTS:
            key = _clip_key(event)
            texts[key] = event

        # Pre-alert clips: "power rune in 30 seconds"
        for event in EVENTS:
            key = _clip_key(event)
            for delay in SUPPORTED_DELAYS:
                clip_name = f"{key}_pre_{delay}"
                texts[clip_name] = f"{event} in {delay} seconds"

        total = len(texts)
        done = 0

        for clip_name, text in texts.items():
            path = os.path.join(self._clip_dir, f"{clip_name}.wav")
            engine.save_to_file(text, path)
            self._clips[clip_name] = path
            done += 1
            if on_progress:
                on_progress(done, total)

        # pyttsx3 processes all saves in one runAndWait call
        engine.runAndWait()
        engine.stop()

    # ── Playback ──────────────────────────────────────────────────

    def play(self, clip_name: str) -> None:
        """Thread-safe enqueue of a clip by name."""
        if clip_name in self._clips:
            self._queue.put(clip_name)

    def _playback_loop(self) -> None:
        while True:
            clip_name = self._queue.get()
            if clip_name is _SENTINEL:
                break
            path = self._clips.get(clip_name)
            if not path or not os.path.isfile(path):
                continue
            try:
                sound = pygame.mixer.Sound(path)
                sound.play()
                # Wait for playback to finish before playing next clip
                pygame.time.wait(int(sound.get_length() * 1000) + 50)
            except pygame.error:
                pass

    # ── Lifecycle ───────────────────────────────────────────────────

    def shutdown(self) -> None:
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=3)
        if self._mixer_ok:
            pygame.mixer.quit()
        shutil.rmtree(self._clip_dir, ignore_errors=True)
