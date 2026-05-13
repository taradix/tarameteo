#ifndef MOCK_ARDUINO_CORE_H
#define MOCK_ARDUINO_CORE_H

#include "../../../lib/CertificateManager/include/IArduino.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <string>

class MockArduino : public IArduino {
public:
    MockArduino() : _millis(0), _epochSeconds(1700000000UL), restartCalled(false) {}

    unsigned long millis() override {
        return _millis;
    }

    unsigned long currentEpochSeconds() override {
        return _epochSeconds;
    }

    void delay(unsigned long ms) override {
        _millis += ms;
    }

    void log(const char* message) override {
        if (message) {
            logMessages.push_back(std::string(message));
        }
    }

    void logf(const char* format, ...) override {
        va_list args;
        va_start(args, format);
        char buffer[512];
        vsnprintf(buffer, sizeof(buffer), format, args);
        va_end(args);
        logMessages.push_back(std::string(buffer));
    }

    void restart() override {
        restartCalled = true;
    }

    // Test helpers
    void setMillis(unsigned long ms) {
        _millis = ms;
    }

    void setCurrentEpochSeconds(unsigned long epochSeconds) {
        _epochSeconds = epochSeconds;
    }

    void advanceTime(unsigned long ms) {
        _millis += ms;
    }

    void clearLogs() {
        logMessages.clear();
    }

    bool hasLogContaining(const char* substring) const {
        for (const auto& msg : logMessages) {
            if (msg.find(substring) != std::string::npos) {
                return true;
            }
        }
        return false;
    }

    void reset() {
        _millis = 0;
        _epochSeconds = 1700000000UL;
        restartCalled = false;
        logMessages.clear();
    }

    unsigned long _millis;
    unsigned long _epochSeconds;
    bool restartCalled;
    std::vector<std::string> logMessages;
};

#endif // MOCK_ARDUINO_CORE_H
