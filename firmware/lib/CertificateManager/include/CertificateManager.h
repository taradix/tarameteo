#ifndef CERTIFICATE_MANAGER_H
#define CERTIFICATE_MANAGER_H

#include <Preferences.h>
#include <stdint.h>
#include "IWiFiClient.h"
#include "IArduino.h"

// Forward declarations
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

// Loads the board identity the factory step wrote into NVS (scripts/factory.py):
// client cert + key, CA cert and BLE passkey. The firmware never writes or
// clears them, so an app-only reflash keeps the identity.
class CertificateManager {
public:
    static const int MAX_CERT_SIZE = 4096;
    static const int MAX_KEY_SIZE = 4096;
    static const int MAX_CN_LENGTH = 64;
    static const uint32_t MAX_PASSKEY = 999999;
    // Bytes of UTF-8, so always within the backend's 32 characters (readings.LABEL_MAX_LENGTH).
    static const int MAX_LABEL_BYTES = 32;
    // A DNS name or IPv4 address, at most a full DNS name long.
    static const int MAX_HOST_BYTES = 253;
    // Seconds between readings: at least a minute, at most a day.
    static const uint32_t MIN_INTERVAL = 60;
    static const uint32_t MAX_INTERVAL = 86400;

    // Constructor with dependency injection
    CertificateManager(Preferences& prefs, IArduino* arduino);
    ~CertificateManager();

    // Lifecycle
    // The arguments are what a board uses until it is provisioned with others (config.h).
    bool begin(const MqttServer& defaultServer, uint32_t defaultInterval);
    bool isProvisioned() const;
    bool needsProvisioning() const;

    // Loading & Validation
    bool loadCertificates(IWiFiClient& client);
    bool validateCertificates();

    // Provisioning: validates, joins the WiFi, and only then saves everything.
    // A rejected payload saves nothing, so the board keeps its working settings.
    void setWiFiManager(WiFiManager* wifiManager) { _wifiManager = wifiManager; }
    bool applyProvisioning(const WiFiCredentials& wifi, const Location& location, const char* label,
                           const MqttServer& server, uint32_t interval);
    // What to notify over BLE for the last applyProvisioning: "ok" or "error:<code>",
    // code being ssid, password, location, label, server, port, interval, wifi or storage.
    const char* getProvisioningStatus() const { return _provisioningStatus; }
    static bool isValidLabel(const char* label);
    static bool isValidHost(const char* host);
    static bool isValidInterval(uint32_t interval) { return interval >= MIN_INTERVAL && interval <= MAX_INTERVAL; }

    // Getters
    const char* getLastError() const { return _lastError; }
    const char* getCN() const { return _cn; }  // The sensor ID
    uint32_t getPasskey() const { return _passkey; }
    Location getLocation() const { return _location; }
    const char* getLabel() const { return _label; }  // Empty when the owner gave none
    MqttServer getMqttServer() const { return {_mqttHost, _mqttPort}; }
    uint32_t getInterval() const { return _interval; }  // Seconds between readings

private:
    char _lastError[128];
    char _cn[MAX_CN_LENGTH];
    char _label[MAX_LABEL_BYTES + 1];
    char _mqttHost[MAX_HOST_BYTES + 1];
    uint16_t _mqttPort;
    uint32_t _interval;
    const char* _provisioningStatus;
    uint32_t _passkey;
    Location _location;

    Preferences& _prefs;
    IArduino* _arduino;
    WiFiManager* _wifiManager;

    // Certificate storage buffers
    char* _clientCert;
    char* _clientKey;
    char* _caCert;

    // Certificate parsing
    bool extractCNFromCert(const char* certPem);
    bool validateCertificateFormat(const char* certPem);
    bool validatePrivateKeyFormat(const char* keyPem);

    // NVS operations
    // The keys applyProvisioning writes here, as opposed to the identity and the WiFi credentials.
    static const char* const SETTING_KEYS[];
    static const size_t SETTING_COUNT = 6;
    bool loadFromNVS(const MqttServer& defaultServer, uint32_t defaultInterval);
    bool putSettings(const Location& location, const char* label, const MqttServer& server, uint32_t interval);
    void restoreSettings(const bool (&existed)[SETTING_COUNT]);

    // Utilities
    void clearClientCredentials();
    void clearCACertificate();
    void setError(const char* error);
    bool rejectProvisioning(const char* status, const char* error);
};

#endif // CERTIFICATE_MANAGER_H
