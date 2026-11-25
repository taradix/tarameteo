#ifndef ESP_SLEEP_H_MOCK
#define ESP_SLEEP_H_MOCK

#ifdef UNIT_TEST

#include <stdint.h>

// ESP32 sleep modes
typedef enum {
    ESP_SLEEP_WAKEUP_UNDEFINED,
    ESP_SLEEP_WAKEUP_ALL,
    ESP_SLEEP_WAKEUP_EXT0,
    ESP_SLEEP_WAKEUP_EXT1,
    ESP_SLEEP_WAKEUP_TIMER,
    ESP_SLEEP_WAKEUP_TOUCHPAD,
    ESP_SLEEP_WAKEUP_ULP,
    ESP_SLEEP_WAKEUP_GPIO,
    ESP_SLEEP_WAKEUP_UART,
    ESP_SLEEP_WAKEUP_WIFI,
    ESP_SLEEP_WAKEUP_COCPU,
    ESP_SLEEP_WAKEUP_COCPU_TRAP_TRIG,
    ESP_SLEEP_WAKEUP_BT,
} esp_sleep_wakeup_cause_t;

typedef enum {
    ESP_PD_DOMAIN_RTC_PERIPH,
    ESP_PD_DOMAIN_RTC_SLOW_MEM,
    ESP_PD_DOMAIN_RTC_FAST_MEM,
    ESP_PD_DOMAIN_XTAL,
    ESP_PD_DOMAIN_MAX
} esp_sleep_pd_domain_t;

typedef enum {
    ESP_PD_OPTION_OFF,
    ESP_PD_OPTION_ON,
    ESP_PD_OPTION_AUTO
} esp_sleep_pd_option_t;

// Mock functions
inline esp_sleep_wakeup_cause_t esp_sleep_get_wakeup_cause(void) {
    return ESP_SLEEP_WAKEUP_UNDEFINED;
}

inline void esp_sleep_enable_timer_wakeup(uint64_t time_in_us) {
    (void)time_in_us;
}

inline int esp_sleep_disable_wakeup_source(esp_sleep_wakeup_cause_t source) {
    (void)source;
    return 0;
}

inline void esp_deep_sleep_start(void) {
    // In mock, do nothing (prevents actual sleep)
}

inline void esp_deep_sleep(uint64_t time_in_us) {
    (void)time_in_us;
}

inline void esp_light_sleep_start(void) {
    // In mock, do nothing
}

inline void esp_sleep_pd_config(esp_sleep_pd_domain_t domain, esp_sleep_pd_option_t option) {
    (void)domain;
    (void)option;
}

#endif // UNIT_TEST
#endif // ESP_SLEEP_H_MOCK
