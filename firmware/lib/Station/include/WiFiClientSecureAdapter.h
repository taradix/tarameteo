#ifndef WIFI_CLIENT_SECURE_ADAPTER_H
#define WIFI_CLIENT_SECURE_ADAPTER_H

#include "IWiFiClient.h"
#include <WiFiClientSecure.h>

// Adapter that wraps the real WiFiClientSecure
class WiFiClientSecureAdapter : public IWiFiClient {
public:
    WiFiClientSecureAdapter(WiFiClientSecure& client) : _client(client) {}

    void setCACert(const char* rootCA) override {
        _client.setCACert(rootCA);
    }

    void setCertificate(const char* client_ca) override {
        _client.setCertificate(client_ca);
    }

    void setPrivateKey(const char* private_key) override {
        _client.setPrivateKey(private_key);
    }

private:
    WiFiClientSecure& _client;
};

#endif // WIFI_CLIENT_SECURE_ADAPTER_H
