#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include <Arduino.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Forward declaration
class CertificateManager;

struct WeatherData {
    float temperature;
    float pressure;
    float humidity;
    float altitude;
    int rssi;
    unsigned long timestamp;
    int retryCount;
};

class MqttClient {
public:
    static const int MAX_RETRIES = 3;
    static const int MQTT_BUFFER_SIZE = 512;
    static const int DNS_RETRIES = 3;
    static const int DNS_RETRY_DELAY_MS = 2000;

    MqttClient(const char* server, int port, CertificateManager* certManager);

    bool begin();
    bool connect();
    bool isConnected();
    bool publishWeatherData(const WeatherData& data);
    void disconnect();
    const char* getLastError() const { return _lastError; }
    int getRetryCount() const { return _retryCount; }
    void setCACert(const char* caCert);

private:
    const char* _server;
    int _port;
    CertificateManager* _certManager;
    char _lastError[128];
    int _retryCount;
    char _topic[64];
    char _clientId[32];
    char _lwTopic[64];

    WiFiClient _wifiClient;
    WiFiClientSecure _wifiClientSecure;
    PubSubClient _mqttClient;

    bool buildPayload(const WeatherData& data, char* buffer, size_t size);
    void setError(const char* error);
};

#endif // MQTT_CLIENT_H
