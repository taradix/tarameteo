#ifndef CERTIFICATE_MANAGER_H
#define CERTIFICATE_MANAGER_H

#include <Preferences.h>
#include "IWiFiClient.h"
#include "IWebServer.h"
#include "IWiFi.h"
#include "IArduino.h"

// Forward declaration
class WiFiManager;

class CertificateManager {
public:
    static const int MAX_CERT_SIZE = 4096;
    static const int MAX_KEY_SIZE = 4096;
    static const int MAX_CN_LENGTH = 64;
    static const int CERT_EXPIRY_WARNING_DAYS = 30;

    // Constructor with dependency injection
    CertificateManager(Preferences& prefs, IWiFi* wifi, IArduino* arduino);
    ~CertificateManager();

    // Lifecycle
    bool begin();
    bool isProvisioned() const;
    bool needsProvisioning() const;

    // Loading & Validation
    bool loadCertificates(IWiFiClient& client);
    bool validateCertificates();

    // Provisioning
    bool startProvisioningMode(IWebServer* webServer);
    void stopProvisioningMode();
    void setWiFiManager(WiFiManager* wifiManager) { _wifiManager = wifiManager; }
    void handleProvisioningLoop();  // Must be called repeatedly to service HTTP requests

    // Storage Management
    bool storeCertificates(const char* certPem, const char* keyPem, const char* caCertPem = nullptr);
    bool clearCertificates();

    // Getters
    const char* getLastError() const { return _lastError; }
    const char* getCN() const { return _cn; }
    const char* getSensorName() const { return _cn; }  // Sensor name IS the CN
    unsigned long getExpirationTime() const { return _expiresAt; }
    int getCertificateVersion() const { return _certVersion; }
    bool isProvisioningActive() const { return _provisioningActive; }
    float getLatitude() const { return _latitude; }
    float getLongitude() const { return _longitude; }

private:
    char _serialNumber[65];  // Hex string of serial
    char _lastError[128];
    char _cn[MAX_CN_LENGTH];
    float _latitude;
    float _longitude;
    unsigned long _expiresAt;
    int _certVersion;
    bool _provisioningActive;
    unsigned long _provisioningStartTime;

    Preferences& _prefs;
    IWiFi* _wifi;
    IArduino* _arduino;
    IWebServer* _provisioningServer;
    WiFiManager* _wifiManager;

    // Certificate storage buffers
    char* _clientCert;
    char* _clientKey;
    char* _caCert;

    // Certificate parsing
    bool extractCNFromCert(const char* certPem);
    bool extractExpirationFromCert(const char* certPem);
    bool validateCertificateFormat(const char* certPem);
    bool validatePrivateKeyFormat(const char* keyPem);
    bool validateCertKeyPair(const char* certPem, const char* keyPem);
    void logCertificateInfo(const char* certPem);

    // NVS operations
    bool loadFromNVS();
    bool saveToNVS(const char* certPem, const char* keyPem, const char* caCertPem);

    // Provisioning server
    void setupProvisioningServer();
    void handleProvisionRequest();
    void handleRootRequest();
    void sendResponse(int code, const char* message);

    // Utilities
    void setError(const char* error);
    const char* getLastMACOctet();
};

#endif // CERTIFICATE_MANAGER_H
