#ifndef CERTIFICATE_MANAGER_H
#define CERTIFICATE_MANAGER_H

#include <Preferences.h>
#include "IWiFiClient.h"
#include "IArduino.h"

// Forward declaration
class WiFiManager;

// Loads the board identity the factory step wrote into NVS (scripts/factory.py):
// client cert + key, CA cert and BLE passkey. The firmware never writes or
// clears them, so an app-only reflash keeps the identity.
class CertificateManager {
public:
    static const int MAX_CERT_SIZE = 4096;
    static const int MAX_KEY_SIZE = 4096;
    static const int MAX_CN_LENGTH = 64;
    static const uint32_t MAX_PASSKEY = 999999;

    // Constructor with dependency injection
    CertificateManager(Preferences& prefs, IArduino* arduino);
    ~CertificateManager();

    // Lifecycle
    bool begin();
    bool isProvisioned() const;
    bool needsProvisioning() const;

    // Loading & Validation
    bool loadCertificates(IWiFiClient& client);
    bool validateCertificates();

    // Provisioning
    void setWiFiManager(WiFiManager* wifiManager) { _wifiManager = wifiManager; }
    bool applyProvisioning(const char* wifiSsid, const char* wifiPassword, float latitude, float longitude);

    // Getters
    const char* getLastError() const { return _lastError; }
    const char* getCN() const { return _cn; }
    const char* getSensorName() const { return _cn; }  // Sensor name IS the CN
    uint32_t getPasskey() const { return _passkey; }
    float getLatitude() const { return _latitude; }
    float getLongitude() const { return _longitude; }

private:
    char _lastError[128];
    char _cn[MAX_CN_LENGTH];
    uint32_t _passkey;
    float _latitude;
    float _longitude;

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
    bool loadFromNVS();

    // Utilities
    void clearClientCredentials();
    void clearCACertificate();
    void setError(const char* error);
};

#endif // CERTIFICATE_MANAGER_H
