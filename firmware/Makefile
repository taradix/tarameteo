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

.PHONY: check
check: .pio/libdeps/analysis/integrity.dat include/config.h
	@echo "==> Running static analysis..."
	@$(PIO) run -e analysis -t compiledb
	@find src lib -name '*.cpp' | xargs clang-tidy -p .

.PHONY: test
test: .pio/libdeps/native/integrity.dat include/config.h
	@echo "==> Running unit tests..."
	@$(PIO) test -e native

.PHONY: coverage
coverage: test
	@echo "==> Generating coverage report..."
	@lcov --capture --directory .pio/build/native --output-file coverage.info
	@lcov --remove coverage.info '/usr/*' '*/test/*' '*/.pio/*' --output-file coverage.cleaned.info
	@genhtml coverage.cleaned.info --output-directory coverage_html
	@echo "==> Coverage report generated in coverage_html/index.html"

.PHONY: clean
clean:
	@echo "==> Cleaning build artifacts..."
	@$(PIO) run -t clean
	@rm -rf .pio/build coverage.info coverage.cleaned.info coverage_html

.DEFAULT_GOAL := test
