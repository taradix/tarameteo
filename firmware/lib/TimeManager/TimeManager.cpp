#include "TimeManager.h"
#include <WiFiUdp.h>

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
  // Configure time (in case begin() wasn't called)
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  // Wait for time to be set
  unsigned long startTime = millis();
  while (time(nullptr) < 24 * 3600) { // Wait until we get a valid time (after 1970)
    if (millis() - startTime > _ntpTimeoutMs) {
      updateLastError("NTP sync timeout");
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

void TimeManager::updateLastError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}