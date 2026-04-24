#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Preferences.h>

class WiFiManager {
public:
    static constexpr int MAX_RECONNECT_ATTEMPTS = 3;
    static constexpr int RECONNECT_DELAY_MS = 1000;  // 1 second between attempts

    // Constructor with optional credentials (NULL = load from NVS)
    // This enables "flash once, provision many" for WiFi credentials
    WiFiManager(const char* ssid = nullptr, const char* password = nullptr, int connectTimeoutMs = 30000);
    ~WiFiManager();

    bool begin();
    bool connect();  // Uses stored credentials
    bool reconnect();  // Uses stored credentials
    void disconnect();
    bool isConnected() const;
    int getRSSI() const;
    const char* getIP() const;
    const char* getLastError() const { return _lastError; }
    int getReconnectAttempts() const { return _reconnectAttempts; }
    void resetReconnectAttempts() { _reconnectAttempts = 0; }

    // Provisioning support
    bool isProvisioned() const;
    bool needsProvisioning() const;
    bool storeCredentials(const char* ssid, const char* password);
    bool clearCredentials();
    const char* getSSID() const { return _ssid; }

private:
    char _ssid[32];
    char _password[64];
    char _lastError[128];
    int _reconnectAttempts;
    Preferences _prefs;

    int _connectTimeoutMs;

    void updateLastError(const char* error);
    bool attemptConnection();
    bool loadFromNVS();
    bool saveToNVS();
};

#endif 
