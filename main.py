import tkinter as tk

from audio_engine import AudioEngine
from ui import App


def main() -> None:
    root = tk.Tk()
    root.withdraw()  # hide main window during clip generation

    # Splash screen
    splash = tk.Toplevel()
    splash.title("Dota 2 Timer")
    splash.resizable(False, False)
    label = tk.Label(splash, text="Generating audio clips...", padx=30, pady=20)
    label.pack()
    progress = tk.Label(splash, text="0 / 0", padx=30, pady=10)
    progress.pack()

    audio = AudioEngine()

    def on_progress(done: int, total: int) -> None:
        progress.config(text=f"{done} / {total}")
        splash.update_idletasks()

    splash.update()
    audio.generate_clips(on_progress=on_progress)

    splash.destroy()
    root.deiconify()

    App(root, audio)
    root.mainloop()


if __name__ == "__main__":
    main()
