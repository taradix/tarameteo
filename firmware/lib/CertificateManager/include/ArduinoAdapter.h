#ifndef ARDUINO_ADAPTER_H
#define ARDUINO_ADAPTER_H

#include "IArduino.h"
#include <Arduino.h>
#include <stdarg.h>

// Adapter that wraps real Arduino functions
class ArduinoAdapter : public IArduino {
public:
    unsigned long millis() override {
        return ::millis();
    }

    void delay(unsigned long ms) override {
        ::delay(ms);
    }

    void log(const char* message) override {
        Serial.println(message);
    }

    void logf(const char* format, ...) override {
        va_list args;
        va_start(args, format);
        char buffer[256];
        vsnprintf(buffer, sizeof(buffer), format, args);
        va_end(args);
        Serial.println(buffer);
    }

    void restart() override {
        ESP.restart();
    }
};

#endif // ARDUINO_ADAPTER_H
