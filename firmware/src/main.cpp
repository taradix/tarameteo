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
#include "WiFiAdapter.h"

// BLE provisioning transport
#include "NimBLEProvisionerAdapter.h"

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

  // On a cold boot (power-on or manual reset, not a deep-sleep wakeup), hold
  // briefly so the serial upload tool has time to connect before we potentially
  // sleep on an error.
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED) {
    Serial.printf("Cold boot — %d ms upload window...\n", BOOT_DELAY_MS);
    delay(BOOT_DELAY_MS);
  }

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

  // Provisioning is only needed for WiFi credentials (certs are pre-flashed).
  // Guarded: NimBLEProvisionerAdapter wraps NimBLE, which has no host build, so
  // the analysis (clang-tidy, -DUNIT_TEST) pass skips this device-only glue.
#ifndef UNIT_TEST
  if (wifiManager.needsProvisioning()) {
    // Advertise "TaraMeteo-XXXX" using the last two MAC octets, matching the old AP name scheme.
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char deviceName[24];
    snprintf(deviceName, sizeof(deviceName), "TaraMeteo-%02X%02X", mac[4], mac[5]);

    Serial.println("===========================================");
    Serial.println("PROVISIONING MODE (BLE)");
    Serial.println("===========================================");
    Serial.println("WiFi credentials not found!");
    Serial.printf("Open the TaraMeteo app and connect to: %s\n", deviceName);
    Serial.printf("Pair with passkey: %06u\n", (unsigned)BLE_PASSKEY);
    Serial.println("Then enter WiFi credentials and sensor location.");
    Serial.println("Device will wait up to 5 minutes for provisioning...");
    Serial.println("===========================================");

    NimBLEProvisionerAdapter ble;
    if (!ble.begin(deviceName, BLE_PASSKEY)) {
      Serial.println("Failed to start BLE provisioning!");
      delay(5000);
      ESP.restart();
    }

    unsigned long startTime = millis();
    while (wifiManager.needsProvisioning() && (millis() - startTime) < 300000) {
      if (ble.poll()) {
        bool ok = certManager.applyProvisioning(ble.ssid(), ble.password(), ble.latitude(), ble.longitude());
        ble.notifyStatus(ok ? "ok" : certManager.getLastError());
        if (!ok) {
          Serial.printf("Provisioning rejected: %s\n", certManager.getLastError());
        }
      }
      delay(10); // Small delay to prevent watchdog issues
    }

    ble.stop();

    if (wifiManager.needsProvisioning()) {
      Serial.println("\nProvisioning timeout. Rebooting...");
      delay(2000);
      ESP.restart();
    }

    Serial.println("\nProvisioning completed! Rebooting...");
    delay(1000);
    ESP.restart();
  }
#endif // UNIT_TEST

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

  // Initialize time manager and sync before certificate validation, which needs current time
  if (!timeManager.begin()) {
    printStatus("Time Manager", false, timeManager.getLastError());
    powerManager.sleep();
  }
  printStatus("Time Manager", true);

  Serial.println("Synchronizing time with NTP servers...");
  if (!timeManager.syncTime()) {
    printStatus("Time Sync", false, timeManager.getLastError());
    Serial.println("NTP sync failed. Cannot validate certificate without current time. Sleeping.");
    powerManager.sleep();
  }
  printStatus("Time Sync", true);
  Serial.printf("Current timestamp: %lu\n", timeManager.getCurrentTimestamp());

  char timeString[32];
  if (timeManager.getFormattedTime(timeString, sizeof(timeString))) {
    Serial.printf("Current time: %s\n", timeString);
  }

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
