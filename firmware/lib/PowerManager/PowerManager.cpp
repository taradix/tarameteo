#include "PowerManager.h"

void PowerManager::armWakeup(unsigned long seconds) { esp_sleep_enable_timer_wakeup(seconds * 1000000ULL); }

void PowerManager::sleep() {
  Serial.println("Entering deep sleep...");
  esp_deep_sleep_start();
}
