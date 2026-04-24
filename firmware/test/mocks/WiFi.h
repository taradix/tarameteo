#ifndef WIFI_H
#define WIFI_H

#ifdef UNIT_TEST

#include "Arduino.h"

// WiFi status constants
typedef enum {
    WL_NO_SHIELD = 255,
    WL_IDLE_STATUS = 0,
    WL_NO_SSID_AVAIL = 1,
    WL_SCAN_COMPLETED = 2,
    WL_CONNECTED = 3,
    WL_CONNECT_FAILED = 4,
    WL_CONNECTION_LOST = 5,
    WL_DISCONNECTED = 6
} wl_status_t;

// WiFi mode constants
typedef enum {
    WIFI_OFF = 0,
    WIFI_STA = 1,
    WIFI_AP = 2,
    WIFI_AP_STA = 3
} wifi_mode_t;

// Mock WiFi class
class MockWiFiClass {
public:
    MockWiFiClass() : _status(WL_DISCONNECTED), _rssi(-70) {}

    // Connection management
    wl_status_t begin(const char* ssid, const char* password = nullptr) {
        (void)ssid;
        (void)password;
        _status = WL_CONNECTED;
        return _status;
    }

    void disconnect(bool wifioff = false, bool eraseap = false) {
        (void)wifioff;
        (void)eraseap;
        _status = WL_DISCONNECTED;
    }

    bool reconnect() {
        _status = WL_CONNECTED;
        return true;
    }

    // Status
    wl_status_t status() const {
        return _status;
    }

    bool isConnected() const {
        return _status == WL_CONNECTED;
    }

    // Network info
    IPAddress localIP() const {
        return IPAddress(192, 168, 1, 100);
    }

    IPAddress gatewayIP() const {
        return IPAddress(192, 168, 1, 1);
    }

    IPAddress subnetMask() const {
        return IPAddress(255, 255, 255, 0);
    }

    IPAddress dnsIP(uint8_t dns_no = 0) const {
        (void)dns_no;
        return IPAddress(8, 8, 8, 8);
    }

    const char* macAddress() const {
        return "00:11:22:33:44:55";
    }

    void macAddress(uint8_t* mac) const {
        if (mac) {
            mac[0] = 0x00;
            mac[1] = 0x11;
            mac[2] = 0x22;
            mac[3] = 0x33;
            mac[4] = 0x44;
            mac[5] = 0x55;
        }
    }

    const char* SSID() const {
        return "MockSSID";
    }

    int32_t RSSI() const {
        return _rssi;
    }

    // Mode
    bool mode(wifi_mode_t m) {
        _mode = m;
        return true;
    }

    wifi_mode_t getMode() const {
        return _mode;
    }

    // Configuration
    bool config(IPAddress local_ip, IPAddress gateway, IPAddress subnet, IPAddress dns1 = IPAddress(), IPAddress dns2 = IPAddress()) {
        (void)local_ip;
        (void)gateway;
        (void)subnet;
        (void)dns1;
        (void)dns2;
        return true;
    }

    bool setAutoConnect(bool autoConnect) {
        (void)autoConnect;
        return true;
    }

    bool setAutoReconnect(bool autoReconnect) {
        (void)autoReconnect;
        return true;
    }

    // Access Point (softAP) methods
    bool softAPConfig(IPAddress local_ip, IPAddress gateway, IPAddress subnet) {
        (void)local_ip;
        (void)gateway;
        (void)subnet;
        return true;
    }

    bool softAP(const char* ssid, const char* password = nullptr, int channel = 1, int ssid_hidden = 0, int max_connection = 4) {
        (void)ssid;
        (void)password;
        (void)channel;
        (void)ssid_hidden;
        (void)max_connection;
        return true;
    }

    IPAddress softAPIP() const {
        return IPAddress(192, 168, 4, 1);
    }

    uint8_t softAPgetStationNum() const {
        return 0;
    }

    bool softAPdisconnect(bool wifioff = false) {
        (void)wifioff;
        return true;
    }

    // DNS
    bool hostByName(const char* hostname, IPAddress& result) {
        (void)hostname;
        result = IPAddress(127, 0, 0, 1);
        return true;
    }

    // Mock helpers for testing
    void setStatus(wl_status_t status) {
        _status = status;
    }

    void setRSSI(int32_t rssi) {
        _rssi = rssi;
    }

private:
    wl_status_t _status;
    wifi_mode_t _mode;
    int32_t _rssi;
};

extern MockWiFiClass WiFi;

#endif // UNIT_TEST
#endif // WIFI_H
