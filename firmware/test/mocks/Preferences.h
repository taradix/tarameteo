#ifndef PREFERENCES_H
#define PREFERENCES_H

#ifdef UNIT_TEST

#include <string>
#include <cstring>
#include <map>

// Mock Preferences class for unit testing
class Preferences {
public:
    bool begin(const char* name, bool readOnly = false) {
        _namespace = name;
        _readOnly = readOnly;
        return true;
    }

    void end() {
        // Nothing to do
    }

    size_t putString(const char* key, const char* value) {
        if (!writable(key)) return 0;
        _storage[std::string(key)] = std::string(value);
        return strlen(value);
    }

    size_t getString(const char* key, char* buffer, size_t maxLen) {
        auto it = _storage.find(std::string(key));
        if (it == _storage.end()) {
            buffer[0] = '\0';
            return 0;
        }
        strncpy(buffer, it->second.c_str(), maxLen - 1);
        buffer[maxLen - 1] = '\0';
        return it->second.length();
    }

    size_t putULong(const char* key, unsigned long value) {
        if (!writable(key)) return 0;
        _ulongs[std::string(key)] = value;
        return sizeof(unsigned long);
    }

    unsigned long getULong(const char* key, unsigned long defaultValue) {
        auto it = _ulongs.find(std::string(key));
        if (it == _ulongs.end()) return defaultValue;
        return it->second;
    }

    size_t putInt(const char* key, int value) {
        if (!writable(key)) return 0;
        _ints[std::string(key)] = value;
        return sizeof(int);
    }

    int getInt(const char* key, int defaultValue) {
        auto it = _ints.find(std::string(key));
        if (it == _ints.end()) return defaultValue;
        return it->second;
    }

    size_t putFloat(const char* key, float value) {
        if (!writable(key)) return 0;
        _floats[std::string(key)] = value;
        return sizeof(float);
    }

    float getFloat(const char* key, float defaultValue) {
        auto it = _floats.find(std::string(key));
        if (it == _floats.end()) return defaultValue;
        return it->second;
    }

    bool isKey(const char* key) {
        return _storage.find(std::string(key)) != _storage.end();
    }

    bool clear() {
        _storage.clear();
        _ulongs.clear();
        _ints.clear();
        _floats.clear();
        _failKey.clear();
        return true;
    }

    // Test knob: every put* to this key returns 0, like a full NVS partition.
    void failWritesTo(const char* key) {
        _failKey = key;
    }

private:
    bool writable(const char* key) const {
        return !_readOnly && _failKey != key;
    }

    std::string _namespace;
    bool _readOnly = false;
    std::string _failKey;
    std::map<std::string, std::string> _storage;
    std::map<std::string, unsigned long> _ulongs;
    std::map<std::string, int> _ints;
    std::map<std::string, float> _floats;
};

#endif // UNIT_TEST
#endif // PREFERENCES_H
