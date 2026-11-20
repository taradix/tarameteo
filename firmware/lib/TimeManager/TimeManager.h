#ifndef TIME_MANAGER_H
#define TIME_MANAGER_H

#include <time.h>

class TimeManager {
public:
    TimeManager(int ntpTimeoutMs, unsigned long syncIntervalMs);

    // Initialize time manager
    bool begin();

    // Sync time with NTP servers
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
    unsigned long _lastSyncTime;
    char _lastError[128];
    int _ntpTimeoutMs;
    unsigned long _syncIntervalMs;

    void setError(const char* error);
    bool syncTimeWithNTP();
};

#endif // TIME_MANAGER_H
