#ifndef OTA_UPDATER_H
#define OTA_UPDATER_H

#include <Preferences.h>
#include <stddef.h>
#include <stdint.h>

// The latest image the backend offers a board, as it publishes it retained on
// firmware/<board> (backend/tarameteo/firmware.py).
struct FirmwareManifest {
    static const size_t MAX_VERSION_BYTES = 64; // The backend's NAME_PATTERN
    static const size_t MAX_URL_BYTES = 255;
    char version[MAX_VERSION_BYTES + 1];
    char url[MAX_URL_BYTES + 1];
    uint8_t sha256[32];
    uint32_t size;
};

// False, leaving out unspecified, unless json holds every field, well-formed.
bool parseManifest(const char* json, size_t length, FirmwareManifest& out);

// Whether to look for updates at all: a local build (FIRMWARE_DEV_VERSION) never
// updates, so a release can't overwrite what a developer flashed.
bool updatesEnabled(const char* running, bool autoUpdate);

// Whether to install latest, once updatesEnabled(): another version than the one running,
// and not one that failed here before. Not "newer": publishing an older version rolls back to it.
bool shouldUpdate(const char* running, const char* latest, const char* bad);

// What a board that can't reach the server or read the sensor does next. It sleeps
// and tries again at the next wake, but a new image (pending) can't: sleeping would
// roll it back. So it retries awake until deadlineMs since boot, then rolls back.
enum class OnFailure { Sleep, Retry, Rollback };
OnFailure onFailure(bool pending, unsigned long nowMs, unsigned long deadlineMs);

// Installs images into the inactive app slot, and remembers in NVS the version it
// installed, so the next boot can tell whether it took. The bootloader boots a new
// image once, pending verification; the board confirms it after its first published
// reading (markValid). A reset before that, a crash or a deep-sleep wake, boots the
// previous image again, and begin() then marks the version bad.
//
// NVS: the tarameteo_ota namespace.
class OtaUpdater {
public:
    explicit OtaUpdater(Preferences& prefs);

    // Opens NVS and checks the last install against running, the version this image is.
    bool begin(const char* running);
    // The last version that failed here, which isn't installed again. Empty when none did.
    const char* getBad() const { return _bad; }
    const char* getLastError() const { return _lastError; }

    // Remembers version as the one installed, before restarting into it.
    bool recordTry(const char* version);

    // Device only, defined apart from the host tests.
    // Whether the running image waits for markValid(); a reset now rolls it back.
    bool isPendingVerify();
    // Keeps the running image for good.
    void markValid();
    // Boots the previous image now.
    [[noreturn]] void rollback();
    // Downloads the image into the inactive slot and checks its sha256, then makes it
    // the one to boot. The caller restarts. False, with the error set, changes nothing.
    bool install(const FirmwareManifest& manifest);

private:
    Preferences& _prefs;
    char _bad[FirmwareManifest::MAX_VERSION_BYTES + 1];
    char _lastError[128];

    void setError(const char* error);
};

#endif // OTA_UPDATER_H
