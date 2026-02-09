#!/home/murray/env/bin/python3
import time
import threading
import numpy as np
import sounddevice as sd

import tkinter as tk
from tkinter import ttk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# -----------------------------
# 1) KID-FRIENDLY SETTINGS
# -----------------------------

GPIO_BUZZER_PIN = 18        # Change if your buzzer is on a different GPIO pin
BUZZER_ON_MS = 8            # How long the buzzer beeps (milliseconds). Try 5 to 12.

SAMPLE_RATE = 48000         # Audio samples per second. 48000 is common and good.
RECORD_MS = 60              # Record this long after you press the button
IGNORE_FIRST_MS = 2         # Ignore the first tiny bit (direct buzzer leak)
ECHO_SEARCH_START_MS = 6    # Don’t look for echoes before this time
ECHO_SEARCH_END_MS = 55     # Don’t look for echoes after this time

TUBE_DISTANCE_M = 3.0       # One-way distance to reflecting end (meters). Change for your tube.
# If you're using a 10 ft tube, 10 ft = 3.05 m (roughly). Put your best estimate here.

# -----------------------------
# 2) BUZZER SETUP (SAFE FALLBACK)
# -----------------------------
try:
    from gpiozero import DigitalOutputDevice
    buzzer = DigitalOutputDevice(GPIO_BUZZER_PIN)
    HAVE_BUZZER = True
except Exception:
    # This lets you run the GUI on a laptop too (no buzzer).
    buzzer = None
    HAVE_BUZZER = False


def beep():
    """Turn buzzer on for BUZZER_ON_MS milliseconds."""
    if not HAVE_BUZZER:
        return
    buzzer.on()
    time.sleep(BUZZER_ON_MS / 1000.0)
    buzzer.off()


# -----------------------------
# 3) AUDIO + ECHO FINDING
# -----------------------------

def record_audio():
    """Record RECORD_MS of audio from the default microphone."""
    seconds = RECORD_MS / 1000.0
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    return audio[:, 0]  # make it 1D


def find_echo_time_ms(wave):
    """
    Very simple echo finder:
    - Use absolute value (loudness)
    - Ignore the start (direct buzzer)
    - Find the biggest peak in a time window
    """
    loud = np.abs(wave)

    def ms_to_index(ms):
        return int((ms / 1000.0) * SAMPLE_RATE)

    i0 = ms_to_index(IGNORE_FIRST_MS)
    i1 = ms_to_index(ECHO_SEARCH_START_MS)
    i2 = ms_to_index(ECHO_SEARCH_END_MS)

    # Safety clamps
    i0 = max(0, min(i0, len(loud)))
    i1 = max(0, min(i1, len(loud)))
    i2 = max(0, min(i2, len(loud)))

    # Zero out the part we don't want to consider
    loud[:i1] = 0.0
    loud[i2:] = 0.0

    peak_index = int(np.argmax(loud))
    peak_ms = (peak_index / SAMPLE_RATE) * 1000.0
    return peak_ms


def compute_speed_m_per_s(echo_time_ms):
    """
    If the echo time is round-trip time:
      speed = (2 * distance) / time
    """
    t = echo_time_ms / 1000.0
    if t <= 0:
        return 0.0
    return (2.0 * TUBE_DISTANCE_M) / t


# -----------------------------
# 4) GUI
# -----------------------------

class EchoApp:
    def __init__(self, root):
        self.root = root
        root.title("Echo Speed of Sound (Kid Mode)")

        # Main layout: left controls, right plot
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root, padding=12)
        left.grid(row=0, column=0, sticky="ns")

        right = ttk.Frame(root, padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        # Big button
        self.button = tk.Button(
            left,
            text="MEASURE\nECHO",
            font=("Arial", 28, "bold"),
            width=10,
            height=4,
            command=self.start_measurement_thread
        )
        self.button.pack(pady=(0, 12))

        # Status labels
        self.status = ttk.Label(left, text="Ready.", font=("Arial", 14))
        self.status.pack(pady=6)

        self.result = ttk.Label(left, text="", font=("Arial", 14))
        self.result.pack(pady=6)

        if not HAVE_BUZZER:
            warn = ttk.Label(left, text="(No buzzer detected)\nGPIO not available.", foreground="red")
            warn.pack(pady=(10, 0))

        # Matplotlib plot
        fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = fig.add_subplot(111)
        self.ax.set_title("Waveform")
        self.ax.set_xlabel("Time (ms)")
        self.ax.set_ylabel("Amplitude")

        self.line, = self.ax.plot([], [], linewidth=1)

        self.canvas = FigureCanvasTkAgg(fig, master=right)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")

        # Keep last waveform
        self.last_wave = None

    def start_measurement_thread(self):
        # Don’t freeze the GUI while recording.
        self.button.config(state="disabled")
        self.status.config(text="Measuring...")
        self.result.config(text="")
        t = threading.Thread(target=self.do_measurement, daemon=True)
        t.start()

    def do_measurement(self):
        try:
            # 1) Start recording slightly BEFORE beep so we don’t miss anything
            # (We record and beep “quickly” in the same thread for simplicity.)
            # A more advanced version would do tight sync, but this is good enough.
            wave = self.record_with_beep()

            # 2) Find echo time
            echo_ms = find_echo_time_ms(wave)
            speed = compute_speed_m_per_s(echo_ms)

            # 3) Update GUI (must happen on main thread)
            self.root.after(0, lambda: self.update_display(wave, echo_ms, speed))

        except Exception as e:
            self.root.after(0, lambda: self.show_error(e))

    def record_with_beep(self):
        seconds = RECORD_MS / 1000.0

        # Start recording
        audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")

        # Small pause to ensure recording started
        time.sleep(0.005)

        # Beep
        beep()

        # Wait for recording to finish
        sd.wait()
        return audio[:, 0]

    def update_display(self, wave, echo_ms, speed):
        self.status.config(text="Done!")

        self.result.config(
            text=f"Echo time: {echo_ms:.2f} ms\nSpeed: {speed:.1f} m/s"
        )

        # Plot waveform
        x_ms = np.arange(len(wave)) / SAMPLE_RATE * 1000.0

        self.ax.clear()
        self.ax.set_title("Waveform (click MEASURE to record again)")
        self.ax.set_xlabel("Time (ms)")
        self.ax.set_ylabel("Amplitude")

        self.ax.plot(x_ms, wave, linewidth=1)

        # Draw a vertical line where we think the echo peak is
        self.ax.axvline(echo_ms, linestyle="--", linewidth=1)
        self.canvas.draw()

        self.button.config(state="normal")

    def show_error(self, e):
        self.status.config(text="Error!")
        self.result.config(text=str(e))
        self.button.config(state="normal")


def main():
    # This makes sounddevice use a reasonable default latency.
    sd.default.latency = ("low", "low")

    root = tk.Tk()
    app = EchoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
