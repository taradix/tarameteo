/*
 * TaraMeteo Firmware
 * Weather station using XIAO_ESP32C3 and BME280 sensor
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
#include <Preferences.h>
#include <cmath>
#include <esp_sleep.h>

// CertificateManager adapters
#include "ArduinoAdapter.h"

// BLE provisioning transport
#include "NimBLEProvisionerAdapter.h"

static constexpr unsigned long SERIAL_START_DELAY_MS = 1000;

// Global objects
BME280Sensor sensor(BME280_ADDRESS, BME280_SDA, BME280_SCL, SEA_LEVEL_PRESSURE);

// WiFi credentials are loaded from NVS (supports "flash once, provision many")
WiFiManager wifiManager(WIFI_TIMEOUT_MS);

// CertificateManager dependencies (must be global to persist)
Preferences certPrefs;
ArduinoAdapter arduinoAdapter;
CertificateManager certManager(certPrefs, &arduinoAdapter);

MqttClient mqttClient(MQTT_SERVER, MQTT_PORT, &certManager);
PowerManager powerManager(SLEEP_DURATION);
TimeManager timeManager(NTP_TIMEOUT_MS);

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
  delay(SERIAL_START_DELAY_MS);

  // A cold boot is a power-on or manual reset, not a deep-sleep wakeup. Hold
  // briefly then, so the serial upload tool has time to connect before we
  // potentially sleep on an error.
  const bool coldBoot = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_UNDEFINED;
  if (coldBoot) {
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

  // Load the identity the factory step wrote into NVS (scripts/factory.py)
  Serial.println("Initializing certificate manager...");
  certManager.setWiFiManager(&wifiManager); // Link for unified provisioning
  if (!certManager.begin()) {
    printStatus("Factory Identity", false, certManager.getLastError());
    powerManager.sleep();
  }
  printStatus("Factory Identity", true);
  Serial.printf("Sensor ID: %s\n", certManager.getCN());

  // A board without WiFi credentials waits for them over BLE. A cold boot opens
  // a shorter window too, so the owner can move a board to a new network by
  // power-cycling it, with no chip erase (that would wipe the identity).
  // Deep-sleep wakeups skip it. Guarded: NimBLEProvisionerAdapter wraps NimBLE,
  // which has no host build, so the analysis (clang-tidy, -DUNIT_TEST) pass
  // skips this device-only glue.
#ifndef UNIT_TEST
  // How long provisioning waits: a board without WiFi credentials has nothing else to do.
  constexpr unsigned long UNPROVISIONED_WINDOW_MS = 5 * 60 * 1000;
  constexpr unsigned long COLD_BOOT_WINDOW_MS = 2 * 60 * 1000;
  // Yields so the watchdog doesn't fire
  constexpr unsigned long BLE_POLL_INTERVAL_MS = 10;
  // Lets the client receive the last status
  constexpr unsigned long FINAL_NOTIFY_DELAY_MS = 1000;
  // Lets the serial log drain before ESP.restart()
  constexpr unsigned long RESTART_DELAY_MS = 2000;
  if (wifiManager.needsProvisioning() || coldBoot) {
    // Advertise the sensor ID printed on the sticker next to the passkey.
    const char *deviceName = certManager.getCN();
    unsigned long windowMs = wifiManager.needsProvisioning() ? UNPROVISIONED_WINDOW_MS : COLD_BOOT_WINDOW_MS;

    Serial.println("===========================================");
    Serial.println("PROVISIONING MODE (BLE)");
    Serial.println("===========================================");
    Serial.printf("Open the TaraMeteo app and connect to: %s\n", deviceName);
    Serial.println("Pair with the passkey printed on the sticker.");
    Serial.println("Then enter WiFi credentials, sensor name and location.");
    Serial.printf("Device will wait up to %lu minutes for provisioning...\n", windowMs / 60000);
    Serial.println("===========================================");

    NimBLEProvisionerAdapter ble;
    bool saved = false;
    // A provisioned board skips the window when BLE fails: restarting would
    // be another cold boot, so it would fail again and never publish.
    if (ble.begin(deviceName, certManager.getPasskey(), certManager.getLabel(), certManager.getLatitude(),
                  certManager.getLongitude())) {
      unsigned long startTime = millis();
      while (!saved && (millis() - startTime) < windowMs) {
        if (ble.poll()) {
          ble.notifyStatus("provisioning");
          saved = certManager.applyProvisioning(ble.ssid(), ble.password(), ble.latitude(), ble.longitude(),
                                                ble.label());
          ble.notifyStatus(certManager.getProvisioningStatus());
          if (!saved) {
            Serial.printf("Provisioning rejected: %s\n", certManager.getLastError());
          }
        }
        delay(BLE_POLL_INTERVAL_MS);
      }
      delay(FINAL_NOTIFY_DELAY_MS);
    } else {
      Serial.println("Failed to start BLE provisioning!");
    }
    ble.stop(); // Frees the BLE stack before the WiFi needs the radio

    if (saved) {
      // No restart: that would be a cold boot, opening the window again.
      Serial.println("\nProvisioning completed!");
    } else if (wifiManager.needsProvisioning()) {
      Serial.println("\nProvisioning failed. Rebooting...");
      delay(RESTART_DELAY_MS);
      ESP.restart();
    }
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

  // Sync before TLS, which checks the broker certificate dates
  Serial.println("Synchronizing time with NTP servers...");
  if (!timeManager.syncTime()) {
    printStatus("Time Sync", false, timeManager.getLastError());
    Serial.println("NTP sync failed. Cannot validate the broker certificate without current time. Sleeping.");
    powerManager.sleep();
  }
  printStatus("Time Sync", true);
  Serial.printf("Current timestamp: %lu\n", timeManager.getCurrentTimestamp());

  char timeString[32];
  if (timeManager.getFormattedTime(timeString, sizeof(timeString))) {
    Serial.printf("Current time: %s\n", timeString);
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
  // Check WiFi connection
  if (!wifiManager.isConnected()) {
    Serial.println("WiFi disconnected, attempting to reconnect...");
    if (!wifiManager.reconnect()) {
      printStatus("WiFi Reconnect", false, wifiManager.getLastError());
      powerManager.sleep();
    }
    printStatus("WiFi Reconnect", true);
    Serial.printf("Reconnected to %s (IP: %s)\n", wifiManager.getSSID(), wifiManager.getIP());
  }

  // Read sensor data
  const WeatherData data = {
      sensor.getTemperature(),
      sensor.getPressure(),
      sensor.getHumidity(),
      sensor.getAltitude(),
      wifiManager.getRSSI(),
      timeManager.getCurrentTimestamp(),
      certManager.getLatitude(),
      certManager.getLongitude(),
      certManager.getLabel()
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
  } else {
    printStatus("Data Publish", true);
  }

  // Disconnect from MQTT (reduces power consumption during sleep)
  mqttClient.disconnect();

  // Enter deep sleep regardless of publish status
  Serial.printf("Entering deep sleep for %d seconds...\n", SLEEP_DURATION);
  Serial.println("=====================================\n");
  powerManager.sleep();
}
