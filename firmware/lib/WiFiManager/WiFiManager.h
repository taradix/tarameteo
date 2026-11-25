#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Preferences.h>

// A network to join. Points into buffers the caller owns.
struct WiFiCredentials {
    const char* ssid;
    const char* password;
};

// Joins the WiFi with the credentials provisioning saved in NVS.
class WiFiManager {
public:
    static constexpr int MAX_RECONNECT_ATTEMPTS = 3;
    static constexpr int RECONNECT_DELAY_MS = 1000;  // 1 second between attempts
    static constexpr size_t MAX_SSID_BYTES = 32;      // 802.11 limit
    static constexpr size_t MAX_PASSWORD_BYTES = 64;  // WPA2: 63-character passphrase or 64 hex digits

    // prefs holds the credentials (tarameteo_wifi namespace); injected so tests can inspect it.
    WiFiManager(Preferences& prefs, int connectTimeoutMs);
    ~WiFiManager();

    bool begin();  // Loads the credentials from NVS
    bool connect();  // Uses stored credentials
    bool reconnect();  // Uses stored credentials
    bool isConnected() const;
    int getRSSI() const;
    const char* getIP() const;
    const char* getLastError() const { return _lastError; }

    // Provisioning support
    static bool isValidSsid(const char* ssid);  // 1 to MAX_SSID_BYTES bytes
    static bool isValidPassword(const char* password);  // 1 to MAX_PASSWORD_BYTES bytes
    bool isProvisioned() const;
    bool needsProvisioning() const;
    // Joins with these credentials without saving them or touching the stored ones.
    bool tryConnect(const WiFiCredentials& credentials);
    // Saves the pair, or leaves NVS and memory as they were when a write fails.
    bool storeCredentials(const WiFiCredentials& credentials);
    // Erases the stored pair, so the next boot needs provisioning again.
    bool clearCredentials();
    const char* getSSID() const { return _ssid; }

private:
    char _ssid[MAX_SSID_BYTES + 1];
    char _password[MAX_PASSWORD_BYTES + 1];
    char _lastError[128];
    Preferences& _prefs;

    int _connectTimeoutMs;

    void setError(const char* error);
    bool attemptConnection(const WiFiCredentials& credentials);
    bool loadFromNVS();
    bool saveToNVS(const WiFiCredentials& credentials);
};

#endif // WIFI_MANAGER_H
