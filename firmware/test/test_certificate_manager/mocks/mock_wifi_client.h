#ifndef MOCK_WIFI_CLIENT_H
#define MOCK_WIFI_CLIENT_H

#include "../../../lib/CertificateManager/include/IWiFiClient.h"
#include <string.h>

class MockWiFiClient : public IWiFiClient {
public:
    MockWiFiClient() : caCertSet(false), certificateSet(false), privateKeySet(false) {
        caCert[0] = '\0';
        certificate[0] = '\0';
        privateKey[0] = '\0';
    }

    void setCACert(const char* rootCA) override {
        if (rootCA) {
            strncpy(caCert, rootCA, sizeof(caCert) - 1);
            caCert[sizeof(caCert) - 1] = '\0';
            caCertSet = true;
        }
    }

    void setCertificate(const char* client_ca) override {
        if (client_ca) {
            strncpy(certificate, client_ca, sizeof(certificate) - 1);
            certificate[sizeof(certificate) - 1] = '\0';
            certificateSet = true;
        }
    }

    void setPrivateKey(const char* private_key) override {
        if (private_key) {
            strncpy(privateKey, private_key, sizeof(privateKey) - 1);
            privateKey[sizeof(privateKey) - 1] = '\0';
            privateKeySet = true;
        }
    }

    // Test helpers
    bool caCertSet;
    bool certificateSet;
    bool privateKeySet;
    char caCert[2048];
    char certificate[2048];
    char privateKey[2048];

    void reset() {
        caCertSet = false;
        certificateSet = false;
        privateKeySet = false;
        caCert[0] = '\0';
        certificate[0] = '\0';
        privateKey[0] = '\0';
    }
};

#endif // MOCK_WIFI_CLIENT_H
