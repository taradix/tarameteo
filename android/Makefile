# make runs recipes with cmd on Windows, which can't run ./gradlew.
GRADLE := $(if $(filter Windows_NT,$(OS)),gradlew.bat,./gradlew) --quiet

# Downloads Gradle and the build plugins.
.PHONY: setup
setup:
	@$(GRADLE) help

.PHONY: check
check:
	@$(GRADLE) lintDebug

# Includes the model check against ../backend/openapi.json.
.PHONY: test
test:
	@$(GRADLE) testDebugUnitTest

# ponytail: no coverage gate yet; add Kover when one is wanted.
.PHONY: coverage
coverage: test

.DEFAULT_GOAL := test
