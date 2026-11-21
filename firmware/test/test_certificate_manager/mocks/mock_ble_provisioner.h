#ifndef MOCK_BLE_PROVISIONER_H
#define MOCK_BLE_PROVISIONER_H

#include "../../../lib/BleProvisioning/include/IBleProvisioner.h"
#include "../../../lib/CertificateManager/include/CertificateManager.h"
#include "../../../lib/WiFiManager/WiFiManager.h"
#include <string>

class MockBleProvisioner : public IBleProvisioner {
public:
    // Holds nothing until begin() seeds it with the board's settings, as a real session does.
    MockBleProvisioner() : payloadReady(false), _location{0.0f, 0.0f}, _port(0), _interval(0) {}

    bool begin(const char* deviceName, uint32_t passkey, const char* label, const Location& location,
               const MqttServer& server, uint32_t interval, const uint8_t* networks, size_t networksLength) override {
        (void)deviceName;
        (void)passkey;
        (void)networks;
        (void)networksLength;
        _label = label ? label : "";
        _location = location;
        _host = server.host ? server.host : "";
        _port = server.port;
        _interval = interval;
        return true;
    }

    void stop() override {}

    // Drains the buffered payload exactly once, like the real adapter clearing
    // its ready flag after the main loop consumes a Commit.
    bool poll() override {
        if (!payloadReady) {
            return false;
        }
        payloadReady = false;
        return true;
    }

    WiFiCredentials wifi() override { return {_ssid.c_str(), _password.c_str()}; }
    Location location() override { return _location; }
    const char* label() override { return _label.c_str(); }
    MqttServer mqttServer() override { return {_host.c_str(), _port}; }
    uint32_t interval() override { return _interval; }

    void notifyStatus(const char* status) override {
        lastStatus = status ? std::string(status) : std::string();
    }

    // Test helper: stage a payload the next poll() will surface.
    void setPayload(const WiFiCredentials& wifi, const Location& location, const char* label = "Gazebo") {
        setWiFiPayload(wifi);
        _location = location;
        _label = label;
    }

    // Test helper: stage WiFi alone, as a client that skips the other fields.
    void setWiFiPayload(const WiFiCredentials& wifi) {
        _ssid = wifi.ssid;
        _password = wifi.password;
        payloadReady = true;
    }

    // Test helpers: stage a server or interval on top of the payload, as a client writing them.
    void setServer(const MqttServer& server) {
        _host = server.host;
        _port = server.port;
    }
    void setInterval(uint32_t interval) { _interval = interval; }

    bool payloadReady;
    std::string lastStatus;

private:
    std::string _ssid;
    std::string _password;
    Location _location;
    std::string _label;
    std::string _host;
    uint16_t _port;
    uint32_t _interval;
};

#endif // MOCK_BLE_PROVISIONER_H
