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

    // Test helpers
    bool hasLogContaining(const char* substring) const {
        for (const auto& msg : logMessages) {
            if (msg.find(substring) != std::string::npos) {
                return true;
            }
        }
        return false;
    }

    void reset() {
        logMessages.clear();
    }

    std::vector<std::string> logMessages;
};

#endif // MOCK_ARDUINO_CORE_H
