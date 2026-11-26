#include "OtaUpdater.h"
#include "Firmware.h"

#include <ArduinoJson.h>
#include <string.h>

static bool parseHex(const char *hex, uint8_t *out, size_t bytes) {
  if (!hex || strlen(hex) != bytes * 2) {
    return false;
  }
  for (size_t i = 0; i < bytes * 2; i++) {
    char c = hex[i];
    int v = (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1;
    if (v < 0) {
      return false;
    }
    out[i / 2] = (i % 2) ? (uint8_t)(out[i / 2] | v) : (uint8_t)(v << 4);
  }
  return true;
}

// Copies src into dst when it fits, else false.
template <size_t N> static bool copyField(char (&dst)[N], const char *src) {
  if (!src || src[0] == '\0' || strlen(src) >= N) {
    return false;
  }
  memcpy(dst, src, strlen(src) + 1);
  return true;
}

bool parseManifest(const char *json, size_t length, FirmwareManifest &out) {
  StaticJsonDocument<512> doc;
  if (deserializeJson(doc, json, length)) {
    return false;
  }
  out.size = doc["size"] | 0u;
  // The backend writes the sha256 in lowercase hex (hashlib.hexdigest).
  return out.size > 0 && copyField(out.version, doc["version"].as<const char *>()) &&
         copyField(out.url, doc["url"].as<const char *>()) &&
         parseHex(doc["sha256"].as<const char *>(), out.sha256, sizeof(out.sha256));
}

bool updatesEnabled(const char *running, bool autoUpdate) {
  return autoUpdate && strcmp(running, FIRMWARE_DEV_VERSION) != 0;
}

bool shouldUpdate(const char *running, const char *latest, const char *bad) {
  return latest[0] != '\0' && strcmp(latest, running) != 0 && strcmp(latest, bad) != 0;
}

OtaUpdater::OtaUpdater(Preferences &prefs) : _prefs(prefs) {
  _bad[0] = '\0';
  _lastError[0] = '\0';
}

bool OtaUpdater::begin(const char *running) {
  if (!_prefs.begin("tarameteo_ota", false)) {
    setError("Failed to initialize NVS");
    return false;
  }
  // isKey first: the real getString logs an error for a missing key.
  if (_prefs.isKey("bad")) {
    _prefs.getString("bad", _bad, sizeof(_bad));
  }
  if (_prefs.isKey("tried")) {
    char tried[sizeof(_bad)];
    _prefs.getString("tried", tried, sizeof(tried));
    // Not running the version installed: it never got as far as markValid().
    if (strcmp(tried, running) != 0) {
      memcpy(_bad, tried, sizeof(_bad));
      // Kept until bad is stored, so a failed write gets another go at the next boot.
      if (_prefs.putString("bad", _bad) > 0) {
        _prefs.remove("tried");
      }
    }
  }
  return true;
}

bool OtaUpdater::recordTry(const char *version) {
  if (_prefs.putString("tried", version) == 0) {
    setError("Failed to store the installed version in NVS");
    return false;
  }
  return true;
}

void OtaUpdater::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}

#ifndef UNIT_TEST
#include <Arduino.h>
#include <HTTPClient.h>
#include <Update.h>
#include <WiFiClientSecure.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>

bool OtaUpdater::isPendingVerify() {
  esp_ota_img_states_t state;
  // A board flashed over USB has no OTA state, so isn't pending.
  return esp_ota_get_state_partition(esp_ota_get_running_partition(), &state) == ESP_OK &&
         state == ESP_OTA_IMG_PENDING_VERIFY;
}

void OtaUpdater::markValid() {
  esp_ota_mark_app_valid_cancel_rollback();
  _prefs.remove("tried");
  Serial.println("OtaUpdater: Firmware confirmed");
}

void OtaUpdater::rollback() {
  Serial.println("OtaUpdater: Rolling back to the previous firmware");
  esp_ota_mark_app_invalid_rollback_and_reboot();
  // Only returns when there is no previous image; a restart while pending rolls back all the same.
  ESP.restart();
  for (;;) {
  }
}

bool OtaUpdater::install(const FirmwareManifest &manifest) {
  static const unsigned long READ_TIMEOUT_MS = 30000;
  Serial.printf("OtaUpdater: Installing %s (%lu bytes) from %s\n", manifest.version, (unsigned long)manifest.size,
                manifest.url);

  // No certificate check: the sha256, from the manifest the mTLS MQTT session
  // delivered, vouches for the bytes, whoever serves them.
  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient http;
  if (!http.begin(client, manifest.url)) {
    setError("Invalid firmware URL");
    return false;
  }
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    char error[64];
    snprintf(error, sizeof(error), "Firmware download failed: HTTP %d", code);
    setError(error);
    http.end();
    return false;
  }
  if (http.getSize() != (int)manifest.size) {
    setError("Firmware size differs from the manifest");
    http.end();
    return false;
  }
  if (!Update.begin(manifest.size)) {
    setError(Update.errorString());
    http.end();
    return false;
  }

  // shortcut: the mbedtls 2.28 *_ret API of Arduino core 2, rename these on moving to core 3 (mbedtls 3).
  mbedtls_sha256_context sha;
  mbedtls_sha256_init(&sha);
  mbedtls_sha256_starts_ret(&sha, 0);
  WiFiClient *stream = http.getStreamPtr();
  static uint8_t buffer[4096];
  size_t written = 0;
  unsigned long lastRead = millis();
  while (written < manifest.size && millis() - lastRead < READ_TIMEOUT_MS) {
    size_t available = stream->available();
    if (available == 0) {
      delay(1);
      continue;
    }
    size_t want = min(min(available, sizeof(buffer)), (size_t)(manifest.size - written));
    int n = stream->read(buffer, want);
    if (n <= 0 || Update.write(buffer, n) != (size_t)n) {
      break;
    }
    mbedtls_sha256_update_ret(&sha, buffer, n);
    written += n;
    lastRead = millis();
  }
  uint8_t digest[32];
  mbedtls_sha256_finish_ret(&sha, digest);
  mbedtls_sha256_free(&sha);
  http.end();

  if (written != manifest.size) {
    Update.abort();
    setError("Firmware download stopped short");
    return false;
  }
  if (memcmp(digest, manifest.sha256, sizeof(digest)) != 0) {
    Update.abort();
    setError("Firmware sha256 differs from the manifest");
    return false;
  }
  // Checks the image (chip, header) and makes it the one to boot.
  if (!Update.end()) {
    setError(Update.errorString());
    return false;
  }
  // Not recorded, the next boot couldn't tell a rollback from success, and would retry the image.
  if (!recordTry(manifest.version)) {
    esp_ota_set_boot_partition(esp_ota_get_running_partition());
    return false;
  }
  Serial.println("OtaUpdater: Installed, restarting");
  return true;
}
#endif // UNIT_TEST
