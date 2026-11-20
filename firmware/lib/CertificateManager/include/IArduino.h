#ifndef I_ARDUINO_H
#define I_ARDUINO_H

// The logging CertificateManager needs, so tests can check what it reports.
class IArduino {
public:
    virtual ~IArduino() {}

    virtual void log(const char* message) = 0;
    virtual void logf(const char* format, ...) = 0;
};

#endif // I_ARDUINO_H
