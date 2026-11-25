#ifndef I_WIFI_CLIENT_H
#define I_WIFI_CLIENT_H

class IWiFiClient {
public:
    virtual ~IWiFiClient() {}
    virtual void setCACert(const char* rootCA) = 0;
    virtual void setCertificate(const char* client_ca) = 0;
    virtual void setPrivateKey(const char* private_key) = 0;
};

#endif // I_WIFI_CLIENT_H
