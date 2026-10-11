SHELL := /bin/sh
.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

UV ?= uv
SERIAL_PORT ?=
FIRMWARE ?= $(ROOT_DIR)/micropython/ESP32_GENERIC-20260824-v1.29.0.bin
FLASH_BAUD ?= 460800
FLASH_OFFSET ?= 0x1000
UPLOAD_FILES ?= $(notdir $(wildcard $(ROOT_DIR)/*.py $(ROOT_DIR)/*.mpy $(ROOT_DIR)/lib))

.PHONY: help setup flash upload upload-sounds monitor flash-monitor ports

help: ## Show the available project commands.
	@printf "Lian's Halloween project commands\n\n"
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nOverrides: SERIAL_PORT=/dev/cu... FIRMWARE=<path.bin> FLASH_BAUD=460800 FLASH_OFFSET=0x1000\n'
	@printf 'Code upload override: UPLOAD_FILES="*.py lib drivers"\n'

setup: ## Create or refresh the root Python environment with uv.
	cd "$(ROOT_DIR)" && $(UV) sync

flash: ## Flash the MicroPython firmware to the connected ESP32.
	cd "$(ROOT_DIR)" && $(UV) run esptool --baud "$(FLASH_BAUD)" $(if $(SERIAL_PORT),--port "$(SERIAL_PORT)",) write-flash "$(FLASH_OFFSET)" "$(FIRMWARE)"

upload: ## Upload Python files and lib/, skipping unchanged files.
	cd "$(ROOT_DIR)" && $(UV) run mpremote connect "$(if $(SERIAL_PORT),$(SERIAL_PORT),auto)" fs cp -r $(UPLOAD_FILES) :
	@printf '\nUpload complete. Run make monitor, then press Ctrl-D to restart main.py.\n'

upload-sounds: ## Upload the entire wavs/ folder, skipping unchanged files.
	cd "$(ROOT_DIR)" && $(UV) run mpremote connect "$(if $(SERIAL_PORT),$(SERIAL_PORT),auto)" fs cp -r wavs :
	@printf '\nSounds uploaded to wavs/. Run make monitor, then press Ctrl-D to restart main.py.\n'

monitor: ## Open the ESP32 serial monitor and MicroPython REPL.
	@printf 'Exit with Ctrl-] or Ctrl-X; Ctrl-C interrupts the running Python program.\n'
	cd "$(ROOT_DIR)" && $(UV) run mpremote connect "$(if $(SERIAL_PORT),$(SERIAL_PORT),auto)" repl

flash-monitor: ## Flash firmware and then open the serial monitor.
	$(MAKE) -C "$(ROOT_DIR)" flash
	$(MAKE) -C "$(ROOT_DIR)" monitor

ports: ## List available serial ports.
	cd "$(ROOT_DIR)" && $(UV) run mpremote connect list
