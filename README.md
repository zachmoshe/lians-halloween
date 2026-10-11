# Lian's Halloween

ESP32 experiments with MicroPython. The root Makefile follows SweetYaar's command
names and `SERIAL_PORT` override convention.

```sh
make setup          # Install the Python tools with uv
make help           # List commands (also the default for plain make)
make flash          # Flash the MicroPython firmware
make upload         # Upload code only, skipping unchanged files
make upload-sounds  # Upload wavs/, skipping unchanged files
make monitor        # Open serial output and the interactive Python prompt
make flash-monitor  # Flash, then monitor
make ports          # List serial ports
```

`make flash` uses `micropython/ESP32_GENERIC-20260824-v1.29.0.bin` at offset
`0x1000` and baud rate `460800`, matching the original flashing command.
It installs the MicroPython runtime; it does not upload the local `main.py`.

`make upload` copies all root `.py` and `.mpy` files (including `main.py` and
`hcsr04.py`), plus the `lib` directory recursively when present.
`make upload-sounds` copies the entire local `wavs/` directory into `wavs/` on
the controller, including any subdirectories. Both commands preserve the
directory structure and use [mpremote's SHA-256 checks](https://docs.micropython.org/en/v1.29.0/reference/mpremote.html#commands)
to skip files already identical on the controller. Existing files with changed
contents are replaced; files only on the controller are left in place.

To include other code directories, override the code upload list with paths
relative to the project root (list only files and directories that exist):

```sh
make upload UPLOAD_FILES='*.py lib drivers'
```

`wavs/scary-sound.wav` is a four-second mono, signed 16-bit little-endian PCM WAV at
22,050 Hz. It has a verified 44-byte WAV header; for this specific file, seek past
those 44 bytes and stream the remaining samples to I2S configured with `bits=16`,
`format=I2S.MONO` and `rate=22050`. Other WAV files may have longer headers.
After `make upload-sounds`, open it on the controller with
`open("wavs/scary-sound.wav", "rb")`.

Exit the monitor before uploading. Uploading interrupts the running program;
afterward, run `make monitor` and press **Ctrl-D** to restart `main.py`, or press
the board's **EN/RESET** button. Code uploads do not require reflashing MicroPython.

The tools select a serial port automatically by default. To choose a board,
especially when multiple devices are connected:

```sh
make flash-monitor SERIAL_PORT=/dev/cu.SLAB_USBtoUART
make upload SERIAL_PORT=/dev/cu.SLAB_USBtoUART
make upload-sounds SERIAL_PORT=/dev/cu.SLAB_USBtoUART
```

Firmware and flashing settings can also be overridden:

```sh
make flash FIRMWARE=micropython/another-firmware.bin FLASH_BAUD=115200
```

The monitor uses [MicroPython's mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html).
Press **Ctrl-C** to interrupt a running program and get the Python prompt, and
**Ctrl-]** or **Ctrl-X** to exit the monitor. Exit the monitor before flashing or uploading.
