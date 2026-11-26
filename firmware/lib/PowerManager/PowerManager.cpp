#include "PowerManager.h"
#ifndef UNIT_TEST
#include <esp_timer.h>
#endif

void PowerManager::armWakeup(unsigned long seconds) { esp_sleep_enable_timer_wakeup(seconds * 1000000ULL); }

void PowerManager::sleep() {
  Serial.println("Entering deep sleep...");
  esp_deep_sleep_start();
}

void PowerManager::sleepUntilPowerCycle() {
  esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_ALL);
  sleep();
}

#ifndef UNIT_TEST
void PowerManager::limitAwake(unsigned long seconds) {
  static esp_timer_handle_t timer = nullptr;
  if (!timer) {
    // Runs on the esp_timer task, so it fires even while the main task is stuck.
    esp_timer_create_args_t args = {};
    args.callback = [](void *) { esp_restart(); };
    args.name = "awake_limit";
    esp_timer_create(&args, &timer);
  }
  esp_timer_stop(timer); // Fails harmlessly when not started
  esp_timer_start_once(timer, (uint64_t)seconds * 1000000ULL);
}
#endif
