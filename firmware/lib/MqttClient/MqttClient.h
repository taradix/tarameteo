#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include <Arduino.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "FactoryIdentity.h"
#include "StationSettings.h"

struct WeatherData {
    float temperature;
    float pressure;
    float humidity;
    float altitude;
    int rssi;
    unsigned long timestamp;
    Location location;
    const char* label;  // Empty when the owner gave none
};

class MqttClient {
public:
    static const int MAX_RETRIES = 3;
    static const int MQTT_BUFFER_SIZE = 512;
    static const int DNS_RETRIES = 3;
    static const int DNS_RETRY_DELAY_MS = 2000;

    // Connects to the settings' MQTT server with the identity's certificates.
    MqttClient(FactoryIdentity& identity, StationSettings& settings);

    bool begin();
    bool connect();
    bool isConnected();
    bool publishWeatherData(const WeatherData& data);
    // Subscribes to topic for its retained message, which the broker sends right after
    // subscribing. Copies it into buffer, NUL-terminated, and returns its length, or 0
    // when none came within timeoutMs or it doesn't fit.
    size_t readRetained(const char* topic, char* buffer, size_t size, unsigned long timeoutMs);
    void disconnect();
    const char* getLastError() const { return _lastError; }

private:
    FactoryIdentity& _identity;
    StationSettings& _settings;
    char _lastError[128];
    char _topic[64];
    char _clientId[32];
    char _lwTopic[64];

    WiFiClientSecure _wifiClientSecure;
    PubSubClient _mqttClient;

    bool buildPayload(const WeatherData& data, int retryCount, char* buffer, size_t size);
    void setError(const char* error);
};

#endif // MQTT_CLIENT_H
