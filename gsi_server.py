import json
import os
import threading
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler


@dataclass
class GameState:
    game_time: float = 0.0
    clock_time: float = 0.0
    paused: bool = False
    game_state: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, game_time: float, clock_time: float, paused: bool, game_state: str) -> None:
        with self._lock:
            self.game_time = game_time
            self.clock_time = clock_time
            self.paused = paused
            self.game_state = game_state

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "game_time": self.game_time,
                "clock_time": self.clock_time,
                "paused": self.paused,
                "game_state": self.game_state,
            }


class _GSIHandler(BaseHTTPRequestHandler):
    """Handles POST requests from Dota 2 Game State Integration."""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        map_data = data.get("map")
        if not map_data:
            return

        game_state: GameState = self.server.game_state  # type: ignore[attr-defined]
        game_state.update(
            game_time=float(map_data.get("game_time", 0)),
            clock_time=float(map_data.get("clock_time", 0)),
            paused=bool(map_data.get("paused", False)),
            game_state=str(map_data.get("game_state", "")),
        )

    def log_message(self, format, *args) -> None:
        # Suppress default HTTP logging
        pass


class GSIServer:
    PORT = 3000

    def __init__(self, game_state: GameState) -> None:
        self.game_state = game_state
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._server = HTTPServer(("127.0.0.1", self.PORT), _GSIHandler)
        self._server.game_state = self.game_state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    @staticmethod
    def write_gsi_config(steam_folder: str) -> None:
        """Write the GSI config file into the Dota 2 cfg directory."""
        cfg_dir = os.path.join(
            steam_folder, "steamapps", "common", "dota 2 beta", "game", "dota", "cfg",
            "gamestate_integration"
        )
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, "gamestate_integration_coach.cfg")
        cfg_content = '''"dota2-timer"
{
    "uri"           "http://127.0.0.1:3000"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "map"           "1"
    }
}
'''
        with open(cfg_path, "w") as f:
            f.write(cfg_content)
