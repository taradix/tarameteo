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

    // Deep sleep with no wakeup: only a power cycle or the reset button starts the board again
    void sleepUntilPowerCycle();

    // Restarts the board once it has been awake this many seconds more, so one that
    // hangs (a stuck connection, a firmware bug) can't drain the battery awake. A new
    // image that hangs restarts before it is confirmed, which rolls it back.
    void limitAwake(unsigned long seconds);
};

#endif // POWER_MANAGER_H
