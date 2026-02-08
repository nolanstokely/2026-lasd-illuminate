#!/home/murray/env/bin/python3
#  Copyright 2026 Nolan Stokely <nolan@stokely.org>

import sys
import time
import gpiozero
from gpiozero import Buzzer
import sounddevice as sd
import numpy as np
import matplotlib.pyplot as plt
SAMPLE_RATE=44100
DURATION=0.05 #seconds
DEVICE=1



def main(args):
    print("hello buster")
    #time.sleep(5)
    #print("i'm sleepy")
    print("Sound devices")
    print(sd.query_devices())
    audio=sd.rec(
        int(SAMPLE_RATE * DURATION),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=DEVICE,
        )

    print("GPIO Debug")
    print(gpiozero.__file__)
    buzzer=Buzzer(21, active_high=True, initial_value=False)
    
    sd.wait()
    buzzer.on()
    #time.sleep(0.01)
    time.sleep(.05)
    buzzer.off()
    buzzer.close()
    
    x=audio.flatten()
    t=np.arange(len(x))/SAMPLE_RATE
    print(f"done. max abs amplitude : {np.max(np.abs(x)):.3f}")
    
    # now we plot the sound wave
    plt.figure()
    plt.plot(t,x)
    plt.title("Nolan's amazing microphone waveform")
    plt.xlabel("time (s)")
    plt.ylabel("amplitude")
    plt.grid(True)
    plt.show()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

