#ifndef MOCK_BLE_PROVISIONER_H
#define MOCK_BLE_PROVISIONER_H

#include "../../../lib/BleProvisioning/include/IBleProvisioner.h"
#include <string>

class MockBleProvisioner : public IBleProvisioner {
public:
    MockBleProvisioner()
        : beginCalled(false), stopCalled(false), passkey(0), payloadReady(false),
          _lat(0.0f), _lon(0.0f) {}

    bool begin(const char* deviceName, uint32_t pk, const char* label) override {
        beginCalled = true;
        deviceNameArg = deviceName ? std::string(deviceName) : std::string();
        passkey = pk;
        _label = label ? label : "";
        return true;
    }

    void stop() override { stopCalled = true; }

    // Drains the buffered payload exactly once, like the real adapter clearing
    // its ready flag after the main loop consumes a Commit.
    bool poll() override {
        if (!payloadReady) {
            return false;
        }
        payloadReady = false;
        return true;
    }

    const char* ssid() override { return _ssid.c_str(); }
    const char* password() override { return _password.c_str(); }
    float latitude() override { return _lat; }
    float longitude() override { return _lon; }
    const char* label() override { return _label.c_str(); }

    void notifyStatus(const char* status) override {
        lastStatus = status ? std::string(status) : std::string();
    }

    // Test helper: stage a payload the next poll() will surface.
    void setPayload(const char* ssid, const char* password, float lat, float lon, const char* label = "Gazebo") {
        _ssid = ssid ? ssid : "";
        _password = password ? password : "";
        _lat = lat;
        _lon = lon;
        _label = label;
        payloadReady = true;
    }

    bool beginCalled;
    bool stopCalled;
    std::string deviceNameArg;
    uint32_t passkey;
    bool payloadReady;
    std::string lastStatus;

private:
    std::string _ssid;
    std::string _password;
    float _lat;
    float _lon;
    std::string _label;
};

#endif // MOCK_BLE_PROVISIONER_H
