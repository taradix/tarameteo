#ifndef ARDUINO_H
#define ARDUINO_H

#ifdef UNIT_TEST

#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdarg.h>
#include <time.h>
#include <string>

// Mock Arduino types
typedef uint8_t byte;
typedef bool boolean;

// Mock Arduino constants
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
// The board's I2C pins, which pins_arduino.h gives each variant (XIAO ESP32C3 values)
static const uint8_t SDA = 6;
static const uint8_t SCL = 7;

// PROGMEM and Flash memory macros (for ArduinoJson compatibility)
#define PROGMEM
#define PGM_P const char*
#define PSTR(s) (s)
#define pgm_read_byte(addr) (*(const unsigned char*)(addr))
#define pgm_read_word(addr) (*(const unsigned short*)(addr))
#define pgm_read_dword(addr) (*(const unsigned long*)(addr))
#define pgm_read_float(addr) (*(const float*)(addr))
#define pgm_read_ptr(addr) (*(void* const*)(addr))
#define strlen_P strlen
#define strcpy_P strcpy
#define strncpy_P strncpy
#define strcmp_P strcmp
#define strncmp_P strncmp
#define memcpy_P memcpy
#define memcmp_P memcmp

// FlashStringHelper mock
class __FlashStringHelper;
#define F(string_literal) (reinterpret_cast<const __FlashStringHelper*>(string_literal))

// Mock Arduino functions (declared but not defined inline to allow override)
unsigned long millis();
void delay(unsigned long ms);
inline void pinMode(uint8_t pin, uint8_t mode) { (void)pin; (void)mode; }
inline void digitalWrite(uint8_t pin, uint8_t val) { (void)pin; (void)val; }
inline int digitalRead(uint8_t pin) { (void)pin; return 0; }

// Mock Print base class
class Print {
public:
    virtual ~Print() {}
    virtual size_t write(uint8_t) { return 1; }
    virtual size_t write(const uint8_t* buffer, size_t size) { (void)buffer; return size; }
    virtual void flush() {}
    size_t print(const char* str) { if(str) printf("%s", str); return str ? strlen(str) : 0; }
    size_t println(const char* str) { if(str) printf("%s\n", str); else printf("\n"); return str ? strlen(str) + 1 : 1; }
    size_t println() { printf("\n"); return 1; }
};

// Mock Stream class
class Stream : public Print {
public:
    virtual int available() { return 0; }
    virtual int read() { return -1; }
    virtual int peek() { return -1; }
    virtual size_t readBytes(char* buffer, size_t length) { (void)buffer; (void)length; return 0; }
    virtual size_t readBytes(uint8_t* buffer, size_t length) { (void)buffer; (void)length; return 0; }
};

// Mock Printable interface
class Printable {
public:
    virtual ~Printable() {}
    virtual size_t printTo(Print& p) const = 0;
};

// Mock Serial class
class MockSerial : public Print {
public:
    void begin(unsigned long baud) { (void)baud; }
    void end() {}
    void println(const char* str) { if(str) printf("%s\n", str); }
    void println(const std::string& str) { printf("%s\n", str.c_str()); }
    void println() { printf("\n"); }
    void print(const char* str) { if(str) printf("%s", str); }
    void print(const std::string& str) { printf("%s", str.c_str()); }
    void printf(const char* format, ...) {
        va_list args;
        va_start(args, format);
        vprintf(format, args);
        va_end(args);
    }
    size_t available() { return 0; }
    int read() { return -1; }
    int peek() { return -1; }
    void flush() {}
};

extern MockSerial Serial;

// String class mock
class String {
public:
    String() : _str("") {}
    String(const char* str) : _str(str ? str : "") {}
    String(const std::string& str) : _str(str) {}
    String(int val) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%d", val);
        _str = buf;
    }
    String(unsigned int val) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%u", val);
        _str = buf;
    }
    String(long val) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%ld", val);
        _str = buf;
    }
    String(unsigned long val) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%lu", val);
        _str = buf;
    }
    String(float val, int precision = 2) {
        char buf[32];
        snprintf(buf, sizeof(buf), "%.*f", precision, val);
        _str = buf;
    }

    const char* c_str() const { return _str.c_str(); }
    size_t length() const { return _str.length(); }
    bool equals(const String& other) const { return _str == other._str; }
    bool equals(const char* other) const { return other && _str == other; }
    int compareTo(const String& other) const { return _str.compare(other._str); }
    bool startsWith(const String& prefix) const {
        return _str.size() >= prefix._str.size() &&
               _str.compare(0, prefix._str.size(), prefix._str) == 0;
    }
    bool endsWith(const String& suffix) const {
        return _str.size() >= suffix._str.size() &&
               _str.compare(_str.size() - suffix._str.size(), suffix._str.size(), suffix._str) == 0;
    }
    int indexOf(char ch, unsigned int fromIndex = 0) const {
        size_t pos = _str.find(ch, fromIndex);
        return (pos == std::string::npos) ? -1 : (int)pos;
    }
    int indexOf(const String& str, unsigned int fromIndex = 0) const {
        size_t pos = _str.find(str._str, fromIndex);
        return (pos == std::string::npos) ? -1 : (int)pos;
    }
    String substring(unsigned int beginIndex) const {
        if (beginIndex > _str.length()) return String();
        return String(_str.substr(beginIndex).c_str());
    }
    String substring(unsigned int beginIndex, unsigned int endIndex) const {
        if (beginIndex > _str.length()) return String();
        if (endIndex > _str.length()) endIndex = _str.length();
        if (beginIndex >= endIndex) return String();
        return String(_str.substr(beginIndex, endIndex - beginIndex).c_str());
    }
    void toLowerCase() {
        for (char& c : _str) c = tolower(c);
    }
    void toUpperCase() {
        for (char& c : _str) c = toupper(c);
    }
    void trim() {
        size_t start = _str.find_first_not_of(" \t\n\r");
        if (start == std::string::npos) { _str = ""; return; }
        size_t end = _str.find_last_not_of(" \t\n\r");
        _str = _str.substr(start, end - start + 1);
    }

    // Concatenation methods
    bool concat(const String& str) {
        _str += str._str;
        return true;
    }
    bool concat(const char* cstr) {
        if (cstr) _str += cstr;
        return true;
    }
    bool concat(char c) {
        _str += c;
        return true;
    }

    // Operators
    String operator+(const String& other) const {
        return String((_str + other._str).c_str());
    }
    String operator+(const char* other) const {
        return String((_str + (other ? other : "")).c_str());
    }
    String& operator+=(const String& other) {
        _str += other._str;
        return *this;
    }
    String& operator+=(const char* other) {
        if (other) _str += other;
        return *this;
    }
    String& operator+=(char ch) {
        _str += ch;
        return *this;
    }
    bool operator==(const String& other) const {
        return _str == other._str;
    }
    bool operator==(const char* other) const {
        return other && _str == other;
    }
    bool operator!=(const String& other) const {
        return _str != other._str;
    }
    bool operator!=(const char* other) const {
        return !other || _str != other;
    }
    char operator[](unsigned int index) const {
        return (index < _str.length()) ? _str[index] : 0;
    }

private:
    std::string _str;
};

// IPAddress mock
class IPAddress {
public:
    IPAddress() { _addr[0] = _addr[1] = _addr[2] = _addr[3] = 0; }
    IPAddress(uint8_t a, uint8_t b, uint8_t c, uint8_t d) {
        _addr[0] = a; _addr[1] = b; _addr[2] = c; _addr[3] = d;
    }
    IPAddress(uint32_t addr) {
        _addr[0] = addr & 0xFF;
        _addr[1] = (addr >> 8) & 0xFF;
        _addr[2] = (addr >> 16) & 0xFF;
        _addr[3] = (addr >> 24) & 0xFF;
    }

    uint8_t operator[](int index) const { return _addr[index & 3]; }
    uint8_t& operator[](int index) { return _addr[index & 3]; }

    operator uint32_t() const {
        return _addr[0] | (_addr[1] << 8) | (_addr[2] << 16) | (_addr[3] << 24);
    }

private:
    uint8_t _addr[4];
};

// ESP mock
class MockESP {
public:
    void restart() {}
    uint32_t getFreeHeap() { return 100000; }
    uint32_t getChipId() { return 12345; }
    const char* getSdkVersion() { return "mock"; }
};

extern MockESP ESP;

// ESP32-specific time configuration function
// Configures SNTP and sets timezone
inline void configTime(long gmtOffset_sec, int daylightOffset_sec,
                       const char* server1, const char* server2 = nullptr,
                       const char* server3 = nullptr) {
    (void)gmtOffset_sec;
    (void)daylightOffset_sec;
    (void)server1;
    (void)server2;
    (void)server3;
}

#endif // UNIT_TEST
#endif // ARDUINO_H
