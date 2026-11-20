#include "PowerManager.h"

PowerManager::PowerManager(unsigned long sleepDurationSeconds) : _sleepDuration(sleepDurationSeconds) {}

void PowerManager::begin() { esp_sleep_enable_timer_wakeup(_sleepDuration * 1000000ULL); }

void PowerManager::sleep() {
  Serial.println("Entering deep sleep...");
  esp_deep_sleep_start();
}
