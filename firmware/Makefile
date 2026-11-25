RUN := uv run
PYTHON := $(RUN) python
PIO := $(RUN) pio
TOUCH := $(PYTHON) -c 'import sys; from pathlib import Path; Path(sys.argv[1]).touch()'

uv.lock: pyproject.toml
	uv lock

include/config.h: include/config.h.example
	@cp -u $< $@

.venv/pyvenv.cfg: uv.lock
	@echo "==> Installing environment..."
	@uv sync --frozen
	@$(TOUCH) $@

.pio/libdeps/%/integrity.dat: .venv/pyvenv.cfg platformio.ini
	@echo "==> Installing $* dependencies..."
	@$(PIO) pkg install -e $*
	@$(TOUCH) $@

.PHONY: setup
setup: .pio/libdeps/esp32/integrity.dat include/config.h
	@echo "==> Building ESP32 firmware..."
	@$(PIO) run -e esp32

.PHONY: factory
factory: .pio/libdeps/esp32/integrity.dat include/config.h
	@echo "==> Flashing firmware and factory identity..."
	@$(PIO) run -e esp32 -t upload $(if $(PORT),--upload-port $(PORT))
	@$(PYTHON) scripts/factory.py $(if $(PORT),--port $(PORT))

# Flashes the app only; NVS keeps the identity and settings.
.PHONY: flash
flash: .pio/libdeps/esp32/integrity.dat include/config.h
	@echo "==> Flashing firmware..."
	@$(PIO) run -e esp32 -t upload $(if $(PORT),--upload-port $(PORT))

.PHONY: monitor
monitor: .venv/pyvenv.cfg
	@$(PIO) device monitor -e esp32 $(if $(PORT),--port $(PORT))

.PHONY: check
check: .pio/libdeps/analysis/integrity.dat include/config.h
	@echo "==> Running static analysis..."
	@$(PIO) run -e analysis -t compiledb
	@find src lib -name '*.cpp' | xargs clang-tidy -p .

.PHONY: test
test: .pio/libdeps/native/integrity.dat include/config.h
	@echo "==> Running unit tests..."
	@$(PIO) test -e native

# Reads the data the last `make test` left in .pio/build/native, like the backend's coverage target.
# Excluded at capture, since CI only restores the build directory, not the library sources in .pio/libdeps.
.PHONY: coverage
coverage:
	@echo "==> Generating coverage report..."
	@lcov --ignore-errors inconsistent,inconsistent --capture --directory .pio/build/native \
		--exclude '/usr/*' --exclude '*/test/*' --exclude '*/.pio/*' --output-file coverage.info
	@genhtml --ignore-errors inconsistent,inconsistent coverage.info --output-directory coverage_html
	@echo "==> Coverage report generated in coverage_html/index.html"

.PHONY: clean
clean:
	@echo "==> Cleaning build artifacts..."
	@$(PIO) run -t clean
	@rm -rf .pio/build coverage.info coverage_html

.DEFAULT_GOAL := test
