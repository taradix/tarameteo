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

# NOTE: no coverage gate yet; add Kover when one is wanted.
# Debug build onto the phone connected over adb.
.PHONY: install
install:
	@$(GRADLE) installDebug

# Signed when the release* properties are set (see build.gradle.kts);
# CI does this on android-v* tags.
.PHONY: release
release:
	@$(GRADLE) assembleRelease bundleRelease
	@echo "==> build/outputs/apk/release/tarameteo-release.apk"
	@echo "==> build/outputs/bundle/release/tarameteo-release.aab"

.PHONY: coverage
coverage: test

.DEFAULT_GOAL := test
