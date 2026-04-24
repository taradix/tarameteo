#ifndef POWER_MANAGER_H
#define POWER_MANAGER_H

#include <Arduino.h>
#include <esp_sleep.h>

class PowerManager {
public:
    // Constructor takes sleep duration in seconds
    PowerManager(unsigned long sleepDurationSeconds);
    
    // Initialize power management
    bool begin();
    
    // Enter deep sleep mode
    void sleep();
    
    // Get last error message
    const char* getLastError() const { return _lastError; }

private:
    unsigned long _sleepDuration;
    char _lastError[128];
};

#endif 