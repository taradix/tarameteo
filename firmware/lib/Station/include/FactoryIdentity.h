#ifndef FACTORY_IDENTITY_H
#define FACTORY_IDENTITY_H

#include <Preferences.h>
#include <stdint.h>
#include "IWiFiClient.h"
#include "IArduino.h"

// Loads the board identity the factory step wrote into NVS (scripts/factory.py):
// client cert + key, CA cert and BLE passkey. The firmware never writes or
// clears them, so an app-only reflash keeps the identity.
//
// NVS: the tarameteo_certs namespace, which StationSettings shares (other keys),
// each through its own Preferences, since one can't be begun twice.
class FactoryIdentity {
public:
    static const int MAX_CERT_SIZE = 4096;
    static const int MAX_KEY_SIZE = 4096;
    static const int MAX_CN_LENGTH = 64;
    static const uint32_t MAX_PASSKEY = 999999;

    FactoryIdentity(Preferences& prefs, IArduino* arduino);
    ~FactoryIdentity();

    // Loads and checks the identity; false, with the error set, when it is missing or malformed.
    bool begin();
    bool isLoaded() const;

    // Loading & Validation
    bool loadCertificates(IWiFiClient& client);
    bool validateCertificates();

    // Getters
    const char* getLastError() const { return _lastError; }
    const char* getCN() const { return _cn; }  // The sensor ID
    uint32_t getPasskey() const { return _passkey; }

private:
    char _lastError[128];
    char _cn[MAX_CN_LENGTH];
    uint32_t _passkey;

    Preferences& _prefs;
    IArduino* _arduino;

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

#endif // FACTORY_IDENTITY_H
