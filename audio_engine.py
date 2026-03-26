import io
import os
import queue
import sys
import threading
import wave
from collections import defaultdict

import pygame


# Silence gap between concatenated clips (seconds)
_GAP_SECONDS = 0.08
# Longer gap between different delay groups in the same second
_GROUP_GAP_SECONDS = 0.25

# Audio format (must match WAV files in assets/voice/)
_RATE = 22050
_CHANNELS = 1
_SAMPWIDTH = 2  # 16-bit

_SENTINEL = None

# Maximum game duration to pre-compute (seconds)
DEFAULT_HORIZON = 90 * 60  # 90 minutes


def _asset_path(filename: str) -> str:
    """Resolve asset path for both dev and PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "voice", filename)


class AudioEngine:
    def __init__(self) -> None:
        self._mixer_ok = False
        try:
            pygame.mixer.init(frequency=_RATE, size=-16, channels=_CHANNELS, buffer=512)
            self._mixer_ok = True
        except pygame.error:
            pass

        self._queue: queue.Queue[bytes | None] = queue.Queue()
        self._clips: dict[str, bytes] = {}  # clip name -> raw PCM frames
        self._schedule: dict[int, bytes] = {}  # game second -> WAV bytes
        self._schedule_lock = threading.Lock()

        # Pre-compute silence gaps as raw PCM bytes
        self._gap = b"\x00" * int(_RATE * _GAP_SECONDS * _SAMPWIDTH)
        self._group_gap = b"\x00" * int(_RATE * _GROUP_GAP_SECONDS * _SAMPWIDTH)

        self._load_clips()

        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    # ── Clip loading ─────────────────────────────────────────────────

    def _load_clips(self) -> None:
        """Load all WAV atoms from assets/voice/ into memory as raw PCM bytes."""
        # Event clips
        for name in ("power_rune", "bounty_rune", "lotus_pool", "wisdom_rune", "neutrals"):
            self._load_one(name, f"{name}.wav")

        # Connector
        self._load_one("and", "and.wav")

        # Time phrases: in_1_second, in_2_seconds, ..., in_60_seconds
        self._load_one("in_1_second", "in_1_second.wav")
        for i in range(2, 61):
            self._load_one(f"in_{i}_seconds", f"in_{i}_seconds.wav")

    def _load_one(self, key: str, filename: str) -> None:
        path = _asset_path(filename)
        if not os.path.isfile(path):
            return
        try:
            with wave.open(path, "rb") as wf:
                self._clips[key] = wf.readframes(wf.getnframes())
        except wave.Error:
            pass

    # ── Phrase assembly ──────────────────────────────────────────────

    def assemble_phrase(self, event_names: list[str], delay: int) -> bytes:
        """Build a combined PCM phrase from atomic clips.

        delay=0:  "power rune" or "power rune and bounty rune"
        delay>0:  "power rune in 30 seconds" or "power rune and bounty rune in 30 seconds"
        """
        parts: list[bytes] = []

        # Event names joined with "and"
        and_clip = self._clips.get("and", b"")
        for i, name in enumerate(event_names):
            clip = self._clips.get(name)
            if clip is None:
                continue
            if i > 0 and and_clip:
                parts.append(self._gap)
                parts.append(and_clip)
            parts.append(self._gap if i > 0 else b"")
            parts.append(clip)

        # Time phrase
        if delay > 0:
            delay = min(delay, 60)
            time_key = f"in_{delay}_second" if delay == 1 else f"in_{delay}_seconds"
            time_clip = self._clips.get(time_key)
            if time_clip:
                parts.append(self._gap)
                parts.append(time_clip)

        return b"".join(parts)

    def _pcm_to_wav_bytes(self, pcm: bytes) -> bytes:
        """Wrap raw PCM frames in a WAV container (in-memory)."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(_SAMPWIDTH)
            wf.setframerate(_RATE)
            wf.writeframes(pcm)
        return buf.getvalue()

    # ── Schedule building ────────────────────────────────────────────

    def build_schedule(
        self,
        events: list[dict],
        enabled: set[str],
        delays: dict[str, list[int]],
        horizon_seconds: int = DEFAULT_HORIZON,
    ) -> None:
        """Pre-compute the full playback schedule with coalescence.

        events: list of {"name", "interval", "start"} dicts
        enabled: set of enabled event names
        delays: dict mapping event name to list of pre-alert delay values
        """
        # Step 1: Build timeline — which events fire at which game second
        # timeline[play_at_second] = list of (event_name, delay_value)
        timeline: dict[int, list[tuple[str, int]]] = defaultdict(list)

        for event in events:
            name = event["name"]
            if name not in enabled:
                continue
            interval = event["interval"]
            start = event["start"]
            event_delays = delays.get(name, [30])

            t = start
            while t <= horizon_seconds:
                # On-time alert
                if t >= 0:
                    timeline[t].append((name, 0))

                # Pre-alerts
                for d in event_delays:
                    if d > 0:
                        play_at = t - d
                        if 0 <= play_at <= horizon_seconds:
                            timeline[play_at].append((name, min(d, 60)))

                t += interval

        # Step 2: For each second, group by delay and assemble phrases
        phrase_cache: dict[str, bytes] = {}
        new_schedule: dict[int, bytes] = {}

        for second, alerts in timeline.items():
            # Group alerts by delay value (same delay = coalesce with "and")
            by_delay: dict[int, list[str]] = defaultdict(list)
            for event_name, delay in alerts:
                if event_name not in by_delay[delay]:
                    by_delay[delay].append(event_name)

            # Assemble one phrase per delay group
            group_pcms: list[bytes] = []
            for delay in sorted(by_delay.keys()):
                names = by_delay[delay]
                cache_key = "+".join(names) + f":{delay}"
                if cache_key not in phrase_cache:
                    phrase_cache[cache_key] = self.assemble_phrase(names, delay)
                group_pcms.append(phrase_cache[cache_key])

            # Concatenate groups with a longer gap between them
            full_pcm = group_pcms[0]
            for pcm in group_pcms[1:]:
                full_pcm += self._group_gap + pcm

            new_schedule[second] = self._pcm_to_wav_bytes(full_pcm)

        with self._schedule_lock:
            self._schedule = new_schedule

    def get_clip_for_second(self, sec: int) -> bytes | None:
        """Thread-safe lookup for a pre-assembled clip at a game second."""
        with self._schedule_lock:
            return self._schedule.get(sec)

    def clear_schedule(self) -> None:
        with self._schedule_lock:
            self._schedule.clear()

    # ── Playback ─────────────────────────────────────────────────────

    def play_wav(self, wav_bytes: bytes) -> None:
        """Thread-safe enqueue of WAV bytes for playback."""
        self._queue.put(wav_bytes)

    def _playback_loop(self) -> None:
        while True:
            wav_bytes = self._queue.get()
            if wav_bytes is _SENTINEL:
                break
            if not self._mixer_ok:
                continue
            try:
                sound = pygame.mixer.Sound(file=io.BytesIO(wav_bytes))
                sound.play()
                pygame.time.wait(int(sound.get_length() * 1000) + 50)
            except pygame.error:
                pass

    # ── Lifecycle ────────────────────────────────────────────────────

    def shutdown(self) -> None:
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=3)
        if self._mixer_ok:
            pygame.mixer.quit()
