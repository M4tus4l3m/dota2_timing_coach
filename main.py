import tkinter as tk

from audio_engine import AudioEngine
from ui import App


def main() -> None:
    root = tk.Tk()
    audio = AudioEngine()
    App(root, audio)
    root.mainloop()


if __name__ == "__main__":
    main()
