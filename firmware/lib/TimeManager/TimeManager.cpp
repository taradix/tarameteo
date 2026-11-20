#include "TimeManager.h"
#include <Arduino.h>

// 2020-01-01T00:00:00Z: the backend treats earlier timestamps as unsynced.
static constexpr time_t MIN_VALID_EPOCH = 1577836800;

TimeManager::TimeManager(int ntpTimeoutMs, unsigned long syncIntervalMs)
    : _timeSynced(false), _lastSyncTime(0), _ntpTimeoutMs(ntpTimeoutMs), _syncIntervalMs(syncIntervalMs) {
  _lastError[0] = '\0';
}

bool TimeManager::begin() {
  // Configure time zone (0 = UTC, adjust as needed)
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  return true;
}

bool TimeManager::syncTime() {
  // Only sync if we haven't synced recently
  if (_timeSynced && (millis() - _lastSyncTime < _syncIntervalMs)) {
    return true;
  }

  return syncTimeWithNTP();
}

bool TimeManager::syncTimeWithNTP() {
  // Wait for the SNTP client started in begin() to set the clock
  unsigned long startTime = millis();
  while (time(nullptr) < MIN_VALID_EPOCH) {
    if (millis() - startTime > _ntpTimeoutMs) {
      setError("NTP sync timeout");
      return false;
    }
    delay(100);
  }

  _timeSynced = true;
  _lastSyncTime = millis();
  return true;
}

unsigned long TimeManager::getCurrentTimestamp() {
  if (!_timeSynced) {
    // Return 0 to signal that no valid time is available.
    // The backend detects pre-2020 timestamps and substitutes server time.
    return 0;
  }
  return time(nullptr);
}

bool TimeManager::getFormattedTime(char *buffer, size_t bufferSize, const char *format) {
  if (!_timeSynced || !buffer || bufferSize == 0) {
    return false;
  }

  time_t now = time(nullptr);
  struct tm *timeinfo = localtime(&now);

  if (!timeinfo) {
    return false;
  }

  return strftime(buffer, bufferSize, format, timeinfo) > 0;
}

void TimeManager::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}
