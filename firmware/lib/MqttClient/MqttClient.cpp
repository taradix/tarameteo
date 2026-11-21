#include "MqttClient.h"
#include "CertificateManager.h"
#include "WiFiClientSecureAdapter.h"
#include <WiFi.h>

MqttClient::MqttClient(CertificateManager *certManager) : _certManager(certManager), _mqttClient(_wifiClientSecure) {

  _lastError[0] = '\0';

  // Topics will be initialized in begin() after certificates are loaded
  _topic[0] = '\0';
  _clientId[0] = '\0';
  _lwTopic[0] = '\0';
}

bool MqttClient::begin() {
  _mqttClient.setBufferSize(MQTT_BUFFER_SIZE);

  // Load client certificates for mTLS authentication
  // Wrap WiFiClientSecure with adapter to match IWiFiClient interface
  WiFiClientSecureAdapter clientAdapter(_wifiClientSecure);
  if (!_certManager->loadCertificates(clientAdapter)) {
    setError("Failed to load certificates for mTLS");
    return false;
  }
  Serial.println("MqttClient: mTLS certificates loaded successfully");

  // Initialize topics using sensor name from certificate CN
  const char *sensorName = _certManager->getCN();
  if (sensorName && strlen(sensorName) > 0) {
    snprintf(_topic, sizeof(_topic), "weather/%s/event", sensorName);
    snprintf(_clientId, sizeof(_clientId), "tarameteo-%s", sensorName);
    snprintf(_lwTopic, sizeof(_lwTopic), "status/%s", sensorName);
    Serial.printf("MqttClient: Initialized for sensor: %s\n", sensorName);
  } else {
    setError("Failed to get sensor name from certificate");
    return false;
  }

  return true;
}

bool MqttClient::connect() {
  if (_mqttClient.connected()) {
    return true;
  }

  // Provisioned over BLE, else the config.h defaults (CertificateManager::begin).
  const MqttServer server = _certManager->getMqttServer();
  Serial.printf("Connecting to MQTT server at %s:%u using mTLS...\n", server.host, (unsigned)server.port);

  // Pre-resolve hostname with retries — DNS over UDP is unreliable at weak signal.
  IPAddress serverIP;
  bool resolved = false;
  for (int i = 0; i < DNS_RETRIES && !resolved; i++) {
    if (i > 0) delay(DNS_RETRY_DELAY_MS);
    resolved = WiFi.hostByName(server.host, serverIP);
  }
  if (!resolved) {
    setError("DNS resolution failed");
    return false;
  }
  // Pass hostname (not IP) so PubSubClient calls connect(hostname) on WiFiClientSecure,
  // giving mbedTLS the name it needs for SNI and DNS-SAN hostname verification.
  (void)serverIP;
  _mqttClient.setServer(server.host, server.port);

  const char *lwMessage = "offline";

  // Connect with mTLS (no username/password needed)
  bool connected = _mqttClient.connect(_clientId,
                                       NULL, // no username (using mTLS)
                                       NULL, // no password (using mTLS)
                                       _lwTopic,
                                       0,    // QoS
                                       true, // retain
                                       lwMessage);

  if (!connected) {
    switch (_mqttClient.state()) {
    case MQTT_CONNECTION_TIMEOUT:
      setError("Connection timeout");
      break;
    case MQTT_CONNECTION_LOST:
      setError("Connection lost");
      break;
    case MQTT_CONNECT_FAILED:
      setError("Connect failed");
      break;
    case MQTT_DISCONNECTED:
      setError("Disconnected");
      break;
    case MQTT_CONNECT_BAD_PROTOCOL:
      setError("Bad protocol");
      break;
    case MQTT_CONNECT_BAD_CLIENT_ID:
      setError("Bad client ID");
      break;
    case MQTT_CONNECT_UNAVAILABLE:
      setError("Unavailable");
      break;
    case MQTT_CONNECT_BAD_CREDENTIALS:
      setError("Bad credentials (mTLS cert issue?)");
      break;
    case MQTT_CONNECT_UNAUTHORIZED:
      setError("Unauthorized (mTLS cert not accepted)");
      break;
    default:
      setError("Unknown error");
      break;
    }
    return false;
  }

  // Publish online status
  _mqttClient.publish(_lwTopic, "online", true);

  Serial.printf("Connected to MQTT server with mTLS (CN=%s)\n", _certManager->getCN());
  return true;
}

bool MqttClient::isConnected() { return _mqttClient.connected(); }

bool MqttClient::publishWeatherData(const WeatherData &data) {
  if (!isConnected()) {
    if (!connect()) {
      return false;
    }
  }

  char payload[MQTT_BUFFER_SIZE];

  // Publish with retries; each attempt reports how many retries preceded it.
  for (int retryCount = 0; retryCount <= MAX_RETRIES; retryCount++) {
    if (retryCount > 0) {
      Serial.printf("Retry attempt %d/%d\n", retryCount, MAX_RETRIES);
      delay(1000 * retryCount);
    }

    if (!buildPayload(data, retryCount, payload, sizeof(payload))) {
      setError("Failed to build JSON payload");
      return false;
    }

    bool success = _mqttClient.publish(_topic, payload, false);

    if (success) {
      Serial.printf("Published to topic: %s\n", _topic);
      // Pump the network loop until the server acknowledges or times out.
      // publish() only writes to the TLS send buffer; without this the WiFi
      // stack is powered down by deep sleep before the packet leaves the chip.
      unsigned long deadline = millis() + 2000;
      while (millis() < deadline && _mqttClient.connected()) {
        _mqttClient.loop();
        delay(10);
      }
      return true;
    }

    if (!isConnected()) {
      Serial.println("Connection lost, attempting to reconnect...");
      if (!connect()) {
        setError("Reconnection failed");
        continue;
      }
    }
  }

  setError("Failed to publish after max retries");
  return false;
}

void MqttClient::disconnect() {
  if (_mqttClient.connected()) {
    _mqttClient.publish(_lwTopic, "offline", true);
    delay(100);
    _mqttClient.loop();
    _mqttClient.disconnect();
    delay(100);
  }
}

bool MqttClient::buildPayload(const WeatherData &data, int retryCount, char *buffer, size_t size) {
  StaticJsonDocument<MQTT_BUFFER_SIZE> doc;

  // The backend parses this payload; keep backend/tests/unit/test_readings.py in sync.
  doc["timestamp"] = data.timestamp;
  doc["temperature"] = data.temperature;
  doc["humidity"] = data.humidity;
  doc["pressure"] = data.pressure;
  doc["latitude"] = data.location.latitude;
  doc["longitude"] = data.location.longitude;

  if (data.label[0] != '\0') {
    doc["label"] = data.label;
  }

  if (data.altitude != 0) {
    doc["altitude"] = data.altitude;
  }

  if (data.rssi != 0) {
    doc["rssi"] = data.rssi;
  }

  if (retryCount > 0) {
    doc["retry_count"] = retryCount;
  }

  size_t len = serializeJson(doc, buffer, size);
  if (len == 0 || len >= size) {
    return false;
  }

  return true;
}

void MqttClient::setError(const char *error) {
  strncpy(_lastError, error, sizeof(_lastError) - 1);
  _lastError[sizeof(_lastError) - 1] = '\0';
}
