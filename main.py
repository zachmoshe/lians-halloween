import math
import select
import time 

import asyncio
import micropython
from machine import I2S, Pin
import neopixel 

from hcsr04 import HCSR04

# Configs

# Audio
DEFAULT_BACKGROUND_VOLUME = 0.3
DEFAULT_BACKGROUND_FILENAME = "wavs/background.wav"
DEFAULT_ONSET_VOLUME = 1.0
DEFAULT_ONSET_FILENAME = "wavs/scary-sound.wav" 

NUM_WAV_BEGINNING_BYTES = 44
AUDIO_RATE = 22050
I2S_BUFFER_SIZE = 8192
I2S_SCK_PIN = 26
I2S_WS_PIN = 25
I2S_SD_PIN = 22
I2S_MODE = I2S.TX
I2S_BITS = 16
I2S_FORMAT = I2S.MONO

# LEDs
NUM_LEDS_IN_STRIP = 10
LED_CYCLE_TIME_MS = 500
LED_GPIO = 15
NORMAL_CYCLE_COLOR = (64, 0, 0)
BLINK_COLOR = (255, 0, 0)
BLINK_TIMES = 5
BLINK_DURATION_MS_ON = 150
BLINK_DURATION_MS_OFF = 150


# HCSR04
DISTANCE_THRESHOLD_CM = 10.0
TRIGGER_PIN = 13
ECHO_PIN = 4


@micropython.viper
def _mix_pcm16_native(buf, bg_buf, onset_buf, bg_samples: int,
                      onset_samples: int, bg_gain: int, onset_gain: int):
    # ESP32 is little-endian. bytearray buffers are aligned for 16-bit access.
    out = ptr16(buf)
    bg = ptr16(bg_buf)
    onset = ptr16(onset_buf)

    for i in range(bg_samples):
        # ptr16 reads unsigned values; convert PCM to signed 16-bit samples.
        a = int(bg[i])
        if a >= 32768:
            a -= 65536
        b = 0
        if i < onset_samples:
            b = int(onset[i])
            if b >= 32768:
                b -= 65536

        # Gains use Q15: 32768 == 1.0. Two unity-gain inputs fit in int32.
        mixed = a * bg_gain + b * onset_gain
        if mixed < 0:
            mixed += 32767  # Round toward zero, like int() in the Python mixer.
        mixed >>= 15
        if mixed > 32767:
            mixed = 32767
        elif mixed < -32768:
            mixed = -32768
        out[i] = mixed & 0xffff


class AudioMixer:

    def __init__(self, background_filename, onset_filename, bg_volume=1.0, onset_volume=1.0):
        assert 0 <= bg_volume <= 1.0
        assert 0 <= onset_volume <= 1.0
        self.bg_volume = bg_volume
        self.onset_volume = onset_volume

        self.audio = I2S(
            0,
            sck=Pin(I2S_SCK_PIN),       # Bit clock
            ws=Pin(I2S_WS_PIN),        # Word select / left-right clock
            sd=Pin(I2S_SD_PIN),        # Audio data output
            mode=I2S_MODE,
            bits=I2S_BITS,
            format=I2S_FORMAT,
            rate=AUDIO_RATE,
            ibuf=I2S_BUFFER_SIZE,
        )
        self.audio_writer = asyncio.StreamWriter(self.audio)

        # Enable nonblocking I2S stream behavior before the first write.
        poll = select.poll()
        poll.register(self.audio, select.POLLOUT)
        poll.poll(0)
        poll.unregister(self.audio)

        # open both files 
        self.background_file = open(background_filename, "rb")
        self.onset_file = open(onset_filename, "rb")

        # skip the WAV header
        self.background_file.seek(NUM_WAV_BEGINNING_BYTES)
        self.onset_file.seek(NUM_WAV_BEGINNING_BYTES)

        self._should_play = False
        self._is_onset = False


    @staticmethod
    def mix_pcm16(buf, bg_buf, onset_buf, bg_n, onset_n, bg_gain, onset_gain):
        # Validate before entering Viper, where pointer access has no bounds checks.
        if bg_n % 2 or onset_n % 2:
            raise ValueError("Incomplete 16-bit sample")
        if not (0 <= bg_n <= len(bg_buf) and bg_n <= len(buf)
                and 0 <= onset_n <= len(onset_buf)):
            raise ValueError("Sample count exceeds buffer size")
        if not (0 <= bg_gain <= 1 and 0 <= onset_gain <= 1):
            raise ValueError("Gains must be between 0 and 1")

        # Convert floats once per chunk, not once per sample.
        bg_q15 = int(bg_gain * 32768 + 0.5)
        onset_q15 = int(onset_gain * 32768 + 0.5)
        _mix_pcm16_native(buf, bg_buf, onset_buf, bg_n // 2,
                          onset_n // 2, bg_q15, onset_q15)

    def play_onset(self):
        self._is_onset = True

    async def play(self):
        self._should_play = True

        buf = bytearray(I2S_BUFFER_SIZE)
        onset_buf = bytearray(I2S_BUFFER_SIZE)
        buf_view = memoryview(buf)

        while self._should_play:
            bg_read_bytes = self.background_file.readinto(buf)
            if bg_read_bytes == 0:
                self.background_file.seek(NUM_WAV_BEGINNING_BYTES)
                bg_read_bytes = self.background_file.readinto(buf)

            if self._is_onset:
                onset_read_bytes = self.onset_file.readinto(onset_buf, bg_read_bytes)
                # detect end of onset file
                if onset_read_bytes == 0:
                    self._is_onset = False
                    self.onset_file.seek(NUM_WAV_BEGINNING_BYTES)

            else:
                onset_read_bytes = 0

            self.mix_pcm16(buf, buf, onset_buf, bg_read_bytes, onset_read_bytes, self.bg_volume, self.onset_volume)

            # A final partial read leaves old samples beyond bg_read_bytes.
            self.audio_writer.write(buf_view[:bg_read_bytes])
            await self.audio_writer.drain()


class Leds:
    def __init__(self, pin, num_leds, cycle_time_ms):
        self.leds = neopixel.NeoPixel(Pin(pin), num_leds)
        self.cycle_time_ms = cycle_time_ms
        self._is_onset = False

    def blink(self, color, times, duration_ms_on=100, duration_ms_off=100):
        self._is_onset = True
        self._color = color
        self._times = times
        self._duration_ms_on = duration_ms_on
        self._duration_ms_off = duration_ms_off
        

    async def play(self):
        phase = 0
        full_cycle = 2 * math.pi
        frame_ms = 20

        while True:
            if self._is_onset:
                # Blink the leds
                for _ in range(self._times):
                    self.leds.fill(self._color)
                    self.leds.write()
                    await asyncio.sleep_ms(self._duration_ms_on)
                    self.leds.fill((0, 0, 0))
                    self.leds.write()
                    await asyncio.sleep_ms(self._duration_ms_off)
                self._is_onset = False

            else: 
                # Regular cycle
                for i in range(self.leds.n):
                    angle = phase + full_cycle * i / self.leds.n
                    intensity = (math.sin(angle) + 1) / 2
                    self.leds[i] = (int(NORMAL_CYCLE_COLOR[0] * intensity), int(NORMAL_CYCLE_COLOR[1] * intensity), int(NORMAL_CYCLE_COLOR[2] * intensity))

                self.leds.write()
                await asyncio.sleep_ms(frame_ms)

                phase = (
                    phase + full_cycle * frame_ms / self.cycle_time_ms
                ) % full_cycle
            
            

async def main():
    sensor = HCSR04(trigger_pin=TRIGGER_PIN, echo_pin=ECHO_PIN)
    audio_mixer = AudioMixer(
        background_filename=DEFAULT_BACKGROUND_FILENAME, 
        onset_filename=DEFAULT_ONSET_FILENAME,
        bg_volume=DEFAULT_BACKGROUND_VOLUME, 
        onset_volume=DEFAULT_ONSET_VOLUME)
    leds = Leds(pin=LED_GPIO, num_leds=NUM_LEDS_IN_STRIP, cycle_time_ms=LED_CYCLE_TIME_MS)

    async def _monitor_distance():
        while True:
            distance = sensor.distance_cm()

            if distance < DISTANCE_THRESHOLD_CM:
                audio_mixer.play_onset()
                leds.blink(BLINK_COLOR, BLINK_TIMES, duration_ms_on=BLINK_DURATION_MS_ON, duration_ms_off=BLINK_DURATION_MS_OFF)

            await asyncio.sleep_ms(100)

    try:
        await asyncio.gather(
            audio_mixer.play(),
            _monitor_distance(),
            leds.play(),
        )
    except Exception as exc:
        print("A task failed:", exc)
        raise  # Preserve the traceback

if __name__ == "__main__":
    asyncio.run(main())
