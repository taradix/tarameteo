#include "PowerManager.h"

PowerManager::PowerManager(unsigned long sleepDurationSeconds) : _sleepDuration(sleepDurationSeconds) {
  _lastError[0] = '\0';
}

bool PowerManager::begin() {
  esp_sleep_enable_timer_wakeup(_sleepDuration * 1000000ULL);
  return true;
}

void PowerManager::sleep() {
  Serial.println("Entering deep sleep...");
  esp_deep_sleep_start();
}