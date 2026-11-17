#ifndef I_ARDUINO_H
#define I_ARDUINO_H

#include <stddef.h>
#include <stdint.h>

class IArduino {
public:
    virtual ~IArduino() {}

    // Time functions
    virtual unsigned long millis() = 0;
    virtual void delay(unsigned long ms) = 0;

    // Serial/logging functions
    virtual void log(const char* message) = 0;
    virtual void logf(const char* format, ...) = 0;

    // System functions
    virtual void restart() = 0;
};

#endif // I_ARDUINO_H
