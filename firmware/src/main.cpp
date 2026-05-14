/*
 * TaraMeteo Firmware
 * Weather station using XIAO_ESP32S3 and BME280 sensor
 *
 * Features:
 * - Deep sleep power management
 * - WiFi connectivity with auto-reconnect
 * - Secure MQTTS (MQTT over TLS) support
 * - Sensor data validation
 * - NTP time synchronization for accurate timestamps
 * - Last Will and Testament for offline detection
 */

#include <Arduino.h>
#include "BME280Sensor.h"
#include "CertificateManager.h"
#include "MqttClient.h"
#include "PowerManager.h"
#include "TimeManager.h"
#include "WiFiManager.h"
#include "config.h"
#include <Arduino.h>
#include <Preferences.h>
#include <cmath>
#include <esp_sleep.h>

// CertificateManager adapters
#include "ArduinoAdapter.h"
#include "WebServerAdapter.h"
#include "WiFiAdapter.h"

// Global objects
BME280Sensor sensor(BME280_ADDRESS, BME280_SDA, BME280_SCL, SEA_LEVEL_PRESSURE);

// WiFi credentials and sensor name will be loaded from NVS (supports "flash once, provision many")
WiFiManager wifiManager(nullptr, nullptr, WIFI_TIMEOUT_MS);

// CertificateManager dependencies (must be global to persist)
Preferences certPrefs;
ArduinoAdapter arduinoAdapter;
WiFiAdapter wifiAdapter;
CertificateManager certManager(certPrefs, &wifiAdapter, &arduinoAdapter);

MqttClient mqttClient(MQTT_SERVER, MQTT_PORT, &certManager);
PowerManager powerManager(SLEEP_DURATION);
TimeManager timeManager(NTP_TIMEOUT_MS, NTP_SYNC_INTERVAL_MS);

void printStatus(const char *component, bool success, const char *error = nullptr) {
  Serial.print(component);
  Serial.print(": ");
  Serial.println(success ? "OK" : "FAILED");
  if (!success && error) {
    Serial.print("  Error: ");
    Serial.println(error);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000); // Give serial connection time to start

  // Configure deep sleep timer before any possible sleep() call.
  powerManager.begin();

  Serial.println("\n=== TaraMeteo Weather Station ===");
  Serial.println("Sensor: (will be determined from certificate CN)");
  Serial.println("Initializing components...");

  // Initialize sensor
  if (!sensor.begin()) {
    printStatus("BME280 Sensor", false, sensor.getLastError());
    powerManager.sleep();
  }
  printStatus("BME280 Sensor", true);

  // Initialize WiFi Manager
  Serial.println("Initializing WiFi manager...");
  if (!wifiManager.begin()) {
    // WiFi credentials not found in NVS - need provisioning
    Serial.println("WiFi credentials not found in NVS");
  }

  // Initialize certificate manager (certs are pre-flashed into firmware)
  Serial.println("Initializing certificate manager...");
  certManager.setWiFiManager(&wifiManager); // Link for unified provisioning
  if (!certManager.begin()) {
    Serial.println("Certificate initialization failed");
  }

  // Provisioning is only needed for WiFi credentials (certs are pre-flashed)
  if (wifiManager.needsProvisioning()) {
    Serial.println("===========================================");
    Serial.println("PROVISIONING MODE");
    Serial.println("===========================================");
    Serial.println("WiFi credentials not found!");
    Serial.println();
    Serial.println("Device is in provisioning mode.");
    Serial.println();
    Serial.println("To provision WiFi and location:");
    Serial.printf("1. Connect to WiFi network: TaraMeteoProv-XXXX\n");
    Serial.println("2. Open browser to: http://192.168.4.1");
    Serial.println("3. Enter WiFi credentials and sensor location");
    Serial.println();
    Serial.println("Device will wait up to 5 minutes for provisioning...");
    Serial.println("===========================================");

    // Start provisioning mode with web server
    WebServerAdapter provisioningServer(80);
    if (!certManager.startProvisioningMode(&provisioningServer)) {
      Serial.println("Failed to start provisioning mode!");
      delay(5000);
      ESP.restart();
    }

    // Wait for provisioning - must call handleProvisioningLoop() to service HTTP requests
    unsigned long startTime = millis();
    unsigned long lastDot = millis();
    while (wifiManager.needsProvisioning() && (millis() - startTime) < 300000) {
      certManager.handleProvisioningLoop(); // Service HTTP requests
      delay(10);                            // Small delay to prevent watchdog issues

      // Print progress dot every second
      if (millis() - lastDot > 1000) {
        Serial.print(".");
        lastDot = millis();
      }
    }

    if (wifiManager.needsProvisioning()) {
      Serial.println("\nProvisioning timeout. Rebooting...");
      delay(2000);
      ESP.restart();
    }

    Serial.println("\nProvisioning completed! Rebooting...");
    delay(1000);
    ESP.restart();
  }

  // Connect to WiFi (credentials now loaded from NVS)
  Serial.println("Connecting to WiFi...");
  if (!wifiManager.connect()) {
    printStatus("WiFi Connection", false, wifiManager.getLastError());
    Serial.println("WiFi connection failed, will retry after sleep.");
    powerManager.sleep();
  }
  printStatus("WiFi Connection", true);
  Serial.printf("Connected to %s (IP: %s)\n", wifiManager.getSSID(), wifiManager.getIP());
  Serial.printf("WiFi RSSI: %d dBm\n", wifiManager.getRSSI());

  // Validate certificates before proceeding
  if (!certManager.validateCertificates()) {
    printStatus("Certificate Validation", false, certManager.getLastError());
    Serial.println("Certificate validation failed. Please re-provision.");
    delay(5000);
    certManager.clearCertificates();
    ESP.restart();
  }
  printStatus("Certificate Validation", true);
  Serial.printf("Certificate CN: %s\n", certManager.getCN());
  Serial.printf("Sensor Name: %s (from certificate)\n", certManager.getSensorName());
  Serial.printf("Certificate expires: %lu\n", certManager.getExpirationTime());

  // Initialize time manager
  if (!timeManager.begin()) {
    printStatus("Time Manager", false, timeManager.getLastError());
    powerManager.sleep();
  }
  printStatus("Time Manager", true);

  // Sync time with NTP servers
  Serial.println("Synchronizing time with NTP servers...");
  if (!timeManager.syncTime()) {
    printStatus("Time Sync", false, timeManager.getLastError());
    Serial.println("Warning: Using device uptime for timestamps");
  } else {
    printStatus("Time Sync", true);
    Serial.printf("Current timestamp: %lu\n", timeManager.getCurrentTimestamp());

    // Display formatted time
    char timeString[32];
    if (timeManager.getFormattedTime(timeString, sizeof(timeString))) {
      Serial.printf("Current time: %s\n", timeString);
    }
  }

  // Initialize MQTT client (certificates already loaded by CertificateManager)
  if (!mqttClient.begin()) {
    printStatus("MQTT Client", false, mqttClient.getLastError());
    powerManager.sleep();
  }
  printStatus("MQTT Client", true);

  // Connect to MQTT broker
  Serial.println("Connecting to MQTT broker...");
  if (!mqttClient.connect()) {
    printStatus("MQTT Connection", false, mqttClient.getLastError());
    // Continue anyway - will retry in loop
  } else {
    printStatus("MQTT Connection", true);
    Serial.printf("Connected to %s:%d\n", MQTT_SERVER, MQTT_PORT);
  }

  Serial.println("All components initialized successfully");
  Serial.printf("Sleep duration: %d seconds (%.1f minutes)\n", SLEEP_DURATION, SLEEP_DURATION / 60.0);
  Serial.println("Starting main loop...\n");
}

void loop() {
  // Check sensor availability
  if (!sensor.isAvailable()) {
    printStatus("Sensor Check", false, sensor.getLastError());
    powerManager.sleep();
  }

  // Check WiFi connection
  if (!wifiManager.isConnected()) {
    Serial.println("WiFi disconnected, attempting to reconnect...");
    if (!wifiManager.reconnect()) {
      printStatus("WiFi Reconnect", false, wifiManager.getLastError());
      Serial.printf("Reconnect attempts: %d/%d\n", wifiManager.getReconnectAttempts(),
                    WiFiManager::MAX_RECONNECT_ATTEMPTS);
      powerManager.sleep();
    }
    printStatus("WiFi Reconnect", true);
    Serial.printf("Reconnected to %s (IP: %s)\n", wifiManager.getSSID(), wifiManager.getIP());
  }

  // Read sensor data
  WeatherData data = {
      sensor.getTemperature(),
      sensor.getPressure(),
      sensor.getHumidity(),
      sensor.getAltitude(),
      wifiManager.getRSSI(),
      timeManager.getCurrentTimestamp(),
      0, // retryCount will be updated by MQTT client
      certManager.getLatitude(),
      certManager.getLongitude()
  };

  // Validate sensor readings
  if (std::isnan(data.temperature) || std::isnan(data.pressure) || std::isnan(data.humidity)) {
    Serial.println("ERROR: Sensor returned invalid readings");
    powerManager.sleep();
  }

  // Print sensor readings
  Serial.println("Sensor Readings:");
  Serial.printf("Temperature: %.1f°C\n", data.temperature);
  Serial.printf("Pressure: %.1f hPa\n", data.pressure);
  Serial.printf("Humidity: %.1f%%\n", data.humidity);
  Serial.printf("Altitude: %.1f m\n", data.altitude);
  Serial.printf("WiFi RSSI: %d dBm\n", data.rssi);
  Serial.printf("Timestamp: %lu\n", data.timestamp);

  // Display formatted time if available
  if (timeManager.isTimeSynced()) {
    char timeString[32];
    if (timeManager.getFormattedTime(timeString, sizeof(timeString))) {
      Serial.printf("Time: %s\n", timeString);
    }
  }

  // Publish data to MQTT broker
  Serial.println("\nPublishing data to MQTT broker...");
  if (!mqttClient.publishWeatherData(data)) {
    printStatus("Data Publish", false, mqttClient.getLastError());
    Serial.printf("Retry count: %d/%d\n", mqttClient.getRetryCount(), MqttClient::MAX_RETRIES);

    // Store retry count for next attempt
    data.retryCount = mqttClient.getRetryCount();
  } else {
    printStatus("Data Publish", true);
    Serial.printf("Data published successfully to topic: weather/%s/event\n", certManager.getSensorName());
  }

  // Disconnect from MQTT (reduces power consumption during sleep)
  mqttClient.disconnect();

  // Enter deep sleep regardless of publish status
  Serial.printf("Entering deep sleep for %d seconds...\n", SLEEP_DURATION);
  Serial.println("=====================================\n");
  powerManager.sleep();
}
