#ifndef POWER_MANAGER_H
#define POWER_MANAGER_H

#include <Arduino.h>
#include <esp_sleep.h>

class PowerManager {
public:
    // Wake from the next sleep() after this many seconds; calling it again replaces the duration
    void armWakeup(unsigned long seconds);

    // Enter deep sleep mode
    void sleep();
};

#endif // POWER_MANAGER_H
