#!/usr/bin/env python3
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

# Tube 1
TUBE_1_NAME = "Tube 1"
TUBE_1_BUZZER_GPIO = 21
#TUBE_1_BUZZER_GPIO = 18
TUBE_1_MIC_DEVICE = 1       # Change after running sd.query_devices()
TUBE_1_DISTANCE_FT = 7.5    # One-way distance in feet

# Tube 2
TUBE_2_NAME = "Tube 2"
TUBE_2_BUZZER_GPIO = 18
#TUBE_2_BUZZER_GPIO = 21
TUBE_2_MIC_DEVICE = 2       # Change after running sd.query_devices()
TUBE_2_DISTANCE_FT = 5.0    # One-way distance in feet

# Shared settings
BUZZER_ON_MS = 8
SAMPLE_RATE = 48000
RECORD_MS = 60
IGNORE_FIRST_MS = 2
ECHO_SEARCH_START_MS = 6
ECHO_SEARCH_END_MS = 55

# -----------------------------
# 2) BUZZER SETUP
# -----------------------------
try:
    from gpiozero import DigitalOutputDevice

    buzzer_1 = DigitalOutputDevice(TUBE_1_BUZZER_GPIO)
    buzzer_2 = DigitalOutputDevice(TUBE_2_BUZZER_GPIO)
    HAVE_BUZZERS = True
except Exception:
    buzzer_1 = None
    buzzer_2 = None
    HAVE_BUZZERS = False


def beep(buzzer):
    """Turn one buzzer on for a short time."""
    if not HAVE_BUZZERS:
        return
    buzzer.on()
    time.sleep(BUZZER_ON_MS / 1000.0)
    buzzer.off()


# -----------------------------
# 3) AUDIO + ECHO FINDING
# -----------------------------

def find_echo_time_ms(wave):
    """Find the loudest echo peak in a time window."""
    loud = np.abs(wave)

    def ms_to_index(ms):
        return int((ms / 1000.0) * SAMPLE_RATE)

    i1 = ms_to_index(ECHO_SEARCH_START_MS)
    i2 = ms_to_index(ECHO_SEARCH_END_MS)

    i1 = max(0, min(i1, len(loud)))
    i2 = max(0, min(i2, len(loud)))

    loud[:i1] = 0.0
    loud[i2:] = 0.0

    peak_index = int(np.argmax(loud))
    peak_ms = (peak_index / SAMPLE_RATE) * 1000.0
    return peak_ms


def compute_speed_ft_per_s(echo_time_ms, distance_ft):
    """
    speed = (2 * distance) / time

    distance_ft is one-way tube distance in feet
    echo_time_ms is round-trip time in milliseconds
    """
    t = echo_time_ms / 1000.0
    if t <= 0:
        return 0.0
    return (2.0 * distance_ft) / t


# -----------------------------
# 4) ONE TUBE PANEL
# -----------------------------

class TubePanel:
    def __init__(self, parent, tube_name, buzzer, mic_device, distance_ft):
        self.tube_name = tube_name
        self.buzzer = buzzer
        self.mic_device = mic_device
        self.distance_ft = distance_ft

        self.frame = ttk.Frame(parent, padding=10, relief="groove")
        self.frame.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        # Big button
        self.button = tk.Button(
            self.frame,
            text=f"MEASURE\n{tube_name}",
            font=("Arial", 22, "bold"),
            width=12,
            height=3,
            command=self.start_measurement_thread,
        )
        self.button.pack(pady=(0, 8))

        # Tube length label
        self.length_label = ttk.Label(
            self.frame,
            text=f"Tube length: {distance_ft:.1f} ft",
            font=("Arial", 14, "bold")
        )
        self.length_label.pack(pady=(0, 10))

        # Status labels
        self.status = ttk.Label(self.frame, text="Ready.", font=("Arial", 12))
        self.status.pack(pady=4)

        self.result = ttk.Label(self.frame, text="", font=("Arial", 12))
        self.result.pack(pady=4)

        # Plot
        self.fig = Figure(figsize=(5, 3.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title(f"{tube_name} Waveform")
        self.ax.set_xlabel("Time (ms)")
        self.ax.set_ylabel("Amplitude")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def start_measurement_thread(self):
        self.button.config(state="disabled")
        self.status.config(text="Measuring...")
        self.result.config(text="")

        t = threading.Thread(target=self.do_measurement, daemon=True)
        t.start()

    def do_measurement(self):
        try:
            wave = self.record_with_beep()
            echo_ms = find_echo_time_ms(wave)
            speed = compute_speed_ft_per_s(echo_ms, self.distance_ft)

            self.frame.after(
                0,
                lambda: self.update_display(wave, echo_ms, speed)
            )

        except Exception as e:
            self.frame.after(0, lambda: self.show_error(e))

    def record_with_beep(self):
        seconds = RECORD_MS / 1000.0

        audio = sd.rec(
            int(seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.mic_device,
        )

        time.sleep(0.005)
        beep(self.buzzer)

        sd.wait()
        return audio[:, 0]

    def update_display(self, wave, echo_ms, speed):
        self.status.config(text="Done!")
        self.result.config(
            text=f"Echo time: {echo_ms:.2f} ms\nSpeed: {speed:.1f} ft/s"
        )

        x_ms = np.arange(len(wave)) / SAMPLE_RATE * 1000.0

        self.ax.clear()
        self.ax.set_title(f"{self.tube_name} Waveform")
        self.ax.set_xlabel("Time (ms)")
        self.ax.set_ylabel("Amplitude")
        self.ax.plot(x_ms, wave, linewidth=1)
        self.ax.axvline(echo_ms, linestyle="--", linewidth=1)
        self.canvas.draw()

        self.button.config(state="normal")

    def show_error(self, e):
        self.status.config(text="Error!")
        self.result.config(text=str(e))
        self.button.config(state="normal")


# -----------------------------
# 5) MAIN GUI
# -----------------------------

def main():
    sd.default.latency = ("low", "low")

    root = tk.Tk()
    root.title("Two Tube Echo Experiment")

    if not HAVE_BUZZERS:
        warning = ttk.Label(
            root,
            text="Warning: buzzers not detected. GUI will still run.",
            foreground="red",
            font=("Arial", 12),
        )
        warning.pack(pady=6)

    main_frame = ttk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    tube_1 = TubePanel(
        main_frame,
        tube_name=TUBE_1_NAME,
        buzzer=buzzer_1,
        mic_device=TUBE_1_MIC_DEVICE,
        distance_ft=TUBE_1_DISTANCE_FT,
    )

    tube_2 = TubePanel(
        main_frame,
        tube_name=TUBE_2_NAME,
        buzzer=buzzer_2,
        mic_device=TUBE_2_MIC_DEVICE,
        distance_ft=TUBE_2_DISTANCE_FT,
    )

    root.mainloop()


if __name__ == "__main__":
    main()
