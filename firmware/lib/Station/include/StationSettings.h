#ifndef STATION_SETTINGS_H
#define STATION_SETTINGS_H

#include <Preferences.h>
#include <stdint.h>
#include "IArduino.h"

class WiFiManager;
struct WiFiCredentials;

// Where the station stands, in degrees.
struct Location {
    float latitude;
    float longitude;
};

// Where the station sends its readings. host points into a buffer the caller owns.
struct MqttServer {
    const char* host;
    uint16_t port;
};

// What provisioning sets on the station besides its WiFi: where it stands, its name,
// where and how often it sends readings, and whether it updates its firmware. Until
// provisioned, a board uses the defaults begin() gets (config.h), no location or name,
// and updates automatically.
//
// NVS: the tarameteo_certs namespace, which FactoryIdentity shares (other keys),
// each through its own Preferences, since one can't be begun twice.
class StationSettings {
public:
    // Bytes of UTF-8, so always within the backend's 32 characters (readings.LABEL_MAX_LENGTH).
    static const int MAX_LABEL_BYTES = 32;
    // A DNS name or IPv4 address, at most a full DNS name long.
    static const int MAX_HOST_BYTES = 253;
    // Seconds between readings: at least a minute, at most a day.
    static const uint32_t MIN_INTERVAL = 60;
    static const uint32_t MAX_INTERVAL = 86400;

    // wifiManager joins and stores the WiFi apply() gets.
    StationSettings(Preferences& prefs, IArduino* arduino, WiFiManager& wifiManager);

    // Loads the provisioned settings, else these defaults, which reset() goes back to.
    // defaultServer.host must outlive this object (config.h's literal does).
    bool begin(const MqttServer& defaultServer, uint32_t defaultInterval);

    // Validates, joins the WiFi, and only then saves everything. A rejected or
    // failed payload changes nothing, in memory or in NVS.
    bool apply(const WiFiCredentials& wifi, const Location& location, const char* label, const MqttServer& server,
               uint32_t interval, bool autoUpdate);
    // Forgets the WiFi first, then everything apply() saved, keeping the factory identity:
    // the board is as it left the factory. A failure halfway leaves the board
    // unprovisioned all the same, so the owner can retry.
    bool reset();
    // What to notify over BLE for the last apply() or reset(): "ok", "reset" or "error:<code>",
    // code being ssid, password, location, label, server, port, interval, wifi or storage.
    const char* getStatus() const { return _status; }
    const char* getLastError() const { return _lastError; }

    static bool isValidLabel(const char* label);
    static bool isValidHost(const char* host);
    static bool isValidInterval(uint32_t interval) { return interval >= MIN_INTERVAL && interval <= MAX_INTERVAL; }

    Location getLocation() const { return _location; }
    const char* getLabel() const { return _label; }  // Empty when the owner gave none
    MqttServer getMqttServer() const { return {_mqttHost, _mqttPort}; }
    uint32_t getInterval() const { return _interval; }  // Seconds between readings
    bool getAutoUpdate() const { return _autoUpdate; }  // Installs the firmware the backend offers

private:
    char _lastError[128];
    const char* _status;
    Location _location;
    char _label[MAX_LABEL_BYTES + 1];
    char _mqttHost[MAX_HOST_BYTES + 1];
    uint16_t _mqttPort;
    uint32_t _interval;
    bool _autoUpdate;
    MqttServer _defaultServer;
    uint32_t _defaultInterval;

    Preferences& _prefs;
    IArduino* _arduino;
    WiFiManager& _wifiManager;

    // The keys apply() writes, as opposed to the identity and the WiFi credentials.
    static const char* const KEYS[];
    static const size_t KEY_COUNT = 7;
    bool put(const Location& location, const char* label, const MqttServer& server, uint32_t interval, bool autoUpdate);
    void restore(const bool (&existed)[KEY_COUNT]);
    void load();

    void setError(const char* error);
    bool reject(const char* status, const char* error);
};

#endif // STATION_SETTINGS_H
