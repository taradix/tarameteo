#ifndef TIME_MANAGER_H
#define TIME_MANAGER_H

#include <time.h>

class TimeManager {
public:
    explicit TimeManager(unsigned long ntpTimeoutMs);

    // Start SNTP and wait up to ntpTimeoutMs for the clock to be set
    bool syncTime();

    // Get current Unix timestamp
    unsigned long getCurrentTimestamp();

    // Get formatted date/time string
    bool getFormattedTime(char* buffer, size_t bufferSize, const char* format = "%Y-%m-%d %H:%M:%S");

    // Check if time is synced
    bool isTimeSynced() const { return _timeSynced; }

    // Get last error message
    const char* getLastError() const { return _lastError; }

private:
    bool _timeSynced;
    char _lastError[128];
    unsigned long _ntpTimeoutMs;

    void setError(const char* error);
};

#endif // TIME_MANAGER_H
