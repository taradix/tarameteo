/*
 * TaraMeteo Firmware
 * Weather station using XIAO_ESP32C3 or XIAO_ESP32S3 and BME280 sensor
 *
 * Features:
 * - Deep sleep power management
 * - WiFi connectivity with auto-reconnect
 * - Secure MQTTS (MQTT over TLS) support
 * - Sensor data validation
 * - NTP time synchronization for accurate timestamps
 * - Last Will and Testament for offline detection
 * - Firmware updates from the backend, rolled back when the new image fails
 */

#include "BME280Sensor.h"
#include "FactoryIdentity.h"
#include "Firmware.h"
#include "MqttClient.h"
#include "OtaUpdater.h"
#include "PowerManager.h"
#include "StationSettings.h"
#include "TimeManager.h"
#include "WiFiManager.h"
#include "config.h"
#include <Arduino.h>
#include <Preferences.h>
#include <cmath>
#include <esp_sleep.h>

// Logging for FactoryIdentity and StationSettings
#include "ArduinoAdapter.h"

// BLE provisioning transport
#include "NetworkList.h"
#include "NimBLEProvisionerAdapter.h"

static constexpr unsigned long SERIAL_START_DELAY_MS = 1000;

// Global objects
BME280Sensor sensor(BME280_ADDRESS, BME280_SDA, BME280_SCL, SEA_LEVEL_PRESSURE);

// WiFi credentials are loaded from NVS (supports "flash once, provision many")
Preferences wifiPrefs;
WiFiManager wifiManager(wifiPrefs, WIFI_TIMEOUT_MS);

// Both keep their keys in the tarameteo_certs namespace, each through its own
// Preferences, since one can't be begun twice. Global, so they outlive setup().
ArduinoAdapter arduinoAdapter;
Preferences identityPrefs;
FactoryIdentity identity(identityPrefs, &arduinoAdapter);
Preferences settingsPrefs;
StationSettings settings(settingsPrefs, &arduinoAdapter, wifiManager);

MqttClient mqttClient(identity, settings);
// The defaults; provisioning over BLE can change them (StationSettings). The board
// sleeps for the interval between readings, sending one each time it wakes.
static_assert(READING_INTERVAL >= StationSettings::MIN_INTERVAL && READING_INTERVAL <= StationSettings::MAX_INTERVAL,
              "READING_INTERVAL must be between 60 seconds (1 minute) and 86400 (1 day)");
static_assert(MQTT_PORT >= 1 && MQTT_PORT <= 65535, "MQTT_PORT must be between 1 and 65535");
PowerManager powerManager;
TimeManager timeManager(NTP_TIMEOUT_MS);

Preferences otaPrefs;
OtaUpdater ota(otaPrefs);
// A new image, booted once: any reset before its first publish rolls it back.
bool pendingVerify = false;
// How long a new image retries reaching the server before rolling back, and how
// long between tries. Within AWAKE_LIMIT_S, which restarts a hung board (and so
// rolls a new image back too).
static constexpr unsigned long PENDING_DEADLINE_MS = 5 * 60 * 1000;
static constexpr unsigned long PENDING_RETRY_MS = 30 * 1000;
static constexpr unsigned long AWAKE_LIMIT_S = 10 * 60;
// The broker sends the retained manifest right after the subscription.
static constexpr unsigned long MANIFEST_TIMEOUT_MS = 1500;

#ifndef UNIT_TEST
// The Arduino core confirms a new image before setup() unless this returns true;
// the board confirms it after its first publish instead (OtaUpdater::markValid).
extern "C" bool verifyRollbackLater() { return true; }
#endif

void printStatus(const char *component, bool success, const char *error = nullptr) {
  Serial.print(component);
  Serial.print(": ");
  Serial.println(success ? "OK" : "FAILED");
  if (!success && error) {
    Serial.print("  Error: ");
    Serial.println(error);
  }
}

// Where the board can't reach the server or read the sensor: it sleeps and tries
// again at the next wake. A new image can't sleep, which would roll it back, so it
// returns to retry awake for a while, then rolls back.
static void retryOrSleep() {
  switch (onFailure(pendingVerify, millis(), PENDING_DEADLINE_MS)) {
  case OnFailure::Retry:
    Serial.printf("New firmware not confirmed yet, retrying in %lu s...\n", PENDING_RETRY_MS / 1000);
    delay(PENDING_RETRY_MS);
    return;
  case OnFailure::Rollback:
    ota.rollback();
  case OnFailure::Sleep:
    powerManager.sleep();
  }
}

// Installs the image the backend offers this board, when it should, and restarts into it.
static void checkForUpdate() {
  if (!updatesEnabled(FIRMWARE_VERSION, settings.getAutoUpdate())) {
    return;
  }
  static char payload[MqttClient::MQTT_BUFFER_SIZE];
  size_t length = mqttClient.readRetained("firmware/" FIRMWARE_BOARD, payload, sizeof(payload), MANIFEST_TIMEOUT_MS);
  if (length == 0) {
    return; // Nothing released for this board yet
  }
  FirmwareManifest manifest;
  if (!parseManifest(payload, length, manifest)) {
    Serial.println("Firmware manifest: invalid, ignored");
    return;
  }
  if (!shouldUpdate(FIRMWARE_VERSION, manifest.version, ota.getBad())) {
    return;
  }
  mqttClient.disconnect(); // Frees its TLS session for the download's
  if (!ota.install(manifest)) {
    printStatus("Firmware Update", false, ota.getLastError());
    return;
  }
  delay(1000); // Lets the serial log drain
  ESP.restart();
}

#ifndef UNIT_TEST
#include <WiFi.h>
#include <vector>

// The scan's networks the board can join, encoded for the Networks characteristic into out. It
// joins with a password only, so open and enterprise networks are left out. Runs before BLE
// starts, so the scan has the radio to itself; it takes a few seconds.
static size_t scanNetworks(uint8_t *out, size_t capacity) {
  WiFi.mode(WIFI_STA);
  int found = WiFi.scanNetworks();
  if (found <= 0) {
    WiFi.scanDelete();
    return 0;
  }
  std::vector<ScannedNetwork> networks;
  networks.reserve(found);
  for (int i = 0; i < found; i++) {
    // The records last until scanDelete(), so their SSIDs need no copy.
    auto *record = static_cast<wifi_ap_record_t *>(WiFi.getScanInfoByIndex(i));
    switch (record->authmode) {
    case WIFI_AUTH_WEP:
    case WIFI_AUTH_WPA_PSK:
    case WIFI_AUTH_WPA2_PSK:
    case WIFI_AUTH_WPA_WPA2_PSK:
    case WIFI_AUTH_WPA3_PSK:
    case WIFI_AUTH_WPA2_WPA3_PSK:
    case WIFI_AUTH_WAPI_PSK:
      networks.push_back({reinterpret_cast<const char *>(record->ssid), record->rssi});
      break;
    default:
      break;
    }
  }
  size_t written = encodeNetworks(networks.data(), networks.size(), out, capacity);
  WiFi.scanDelete();
  Serial.printf("WiFi scan: %d access points, %u networks to offer in %u bytes\n", found, (unsigned)networks.size(),
                (unsigned)written);
  return written;
}
#endif // UNIT_TEST

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
  powerManager.armWakeup(READING_INTERVAL);

  Serial.println("\n=== TaraMeteo Weather Station ===");
  Serial.printf("Firmware %s for %s\n", FIRMWARE_VERSION, FIRMWARE_BOARD);
  // Without its NVS, the board still runs; it just can't tell a failed update.
  if (!ota.begin(FIRMWARE_VERSION)) {
    printStatus("Firmware Updater", false, ota.getLastError());
  }
  pendingVerify = ota.isPendingVerify();
  if (pendingVerify) {
    Serial.println("New firmware: confirming it once a reading is published");
  }
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
  Serial.println("Loading factory identity...");
  if (!identity.begin()) {
    printStatus("Factory Identity", false, identity.getLastError());
    powerManager.sleep();
  }
  printStatus("Factory Identity", true);
  Serial.printf("Sensor ID: %s\n", identity.getCN());

  // What provisioning set, else config.h's defaults
  if (!settings.begin({MQTT_SERVER, MQTT_PORT}, READING_INTERVAL)) {
    printStatus("Station Settings", false, settings.getLastError());
    powerManager.sleep();
  }

  // A board without WiFi credentials waits for them over BLE. A cold boot opens
  // a shorter window too, so the owner can move a board to a new network by
  // power-cycling it, or reset it, with no chip erase (that would wipe the identity).
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
  // Not for a new image, which restarted into itself: a reset before it publishes would roll it back.
  if ((wifiManager.needsProvisioning() || coldBoot) && !pendingVerify) {
    // Advertise the sensor ID printed on the sticker next to the passkey.
    const char *deviceName = identity.getCN();
    unsigned long windowMs = wifiManager.needsProvisioning() ? UNPROVISIONED_WINDOW_MS : COLD_BOOT_WINDOW_MS;

    Serial.println("===========================================");
    Serial.println("PROVISIONING MODE (BLE)");
    Serial.println("===========================================");
    Serial.printf("Open the TaraMeteo app and connect to: %s\n", deviceName);
    Serial.println("Pair with the passkey printed on the sticker.");
    Serial.println("Then enter WiFi credentials, sensor name and location.");
    Serial.printf("Device will wait up to %lu minutes for provisioning...\n", windowMs / 60000);
    Serial.println("===========================================");

    // The networks the app offers to pick from.
    static uint8_t networks[NETWORKS_MAX_BYTES];
    size_t networksLength = scanNetworks(networks, sizeof(networks));

    NimBLEProvisionerAdapter ble;
    bool saved = false;
    bool wiped = false;
    // A provisioned board skips the window when BLE fails: restarting would
    // be another cold boot, so it would fail again and never publish.
    if (ble.begin(deviceName, identity.getPasskey(), settings.getLabel(), settings.getLocation(),
                  settings.getMqttServer(), settings.getInterval(), settings.getAutoUpdate(), networks,
                  networksLength)) {
      unsigned long startTime = millis();
      while (!saved && !wiped && (millis() - startTime) < windowMs) {
        switch (ble.poll()) {
        case BleRequest::Provision:
          ble.notifyStatus("provisioning");
          saved = settings.apply(ble.wifi(), ble.location(), ble.label(), ble.mqttServer(), ble.interval(),
                                 ble.autoUpdate());
          ble.notifyStatus(settings.getStatus());
          if (!saved) {
            Serial.printf("Provisioning rejected: %s\n", settings.getLastError());
          }
          break;
        case BleRequest::Reset:
          wiped = settings.reset();
          ble.notifyStatus(settings.getStatus());
          if (!wiped) {
            Serial.printf("Reset failed: %s\n", settings.getLastError());
          }
          break;
        case BleRequest::Unknown:
          ble.notifyStatus("error:commit");
          break;
        case BleRequest::None:
          break;
        }
        delay(BLE_POLL_INTERVAL_MS);
      }
      delay(FINAL_NOTIFY_DELAY_MS);
    } else {
      Serial.println("Failed to start BLE provisioning!");
    }
    ble.stop(); // Frees the BLE stack before the WiFi needs the radio

    if (wiped) {
      // Not a restart, which would advertise for good with nothing to join: an owner
      // resets a board to shelve it or give it away, and its next power-on sets it up.
      Serial.println("\nReset to factory settings. Sleeping until power-cycled.");
      powerManager.sleepUntilPowerCycle();
    } else if (saved) {
      // No restart: that would be a cold boot, opening the window again.
      Serial.println("\nProvisioning completed!");
    } else if (wifiManager.needsProvisioning()) {
      Serial.println("\nProvisioning failed. Rebooting...");
      delay(RESTART_DELAY_MS);
      ESP.restart();
    }
  }
#endif // UNIT_TEST

  // The provisioned interval, or config.h's, from here on
  powerManager.armWakeup(settings.getInterval());
  powerManager.limitAwake(AWAKE_LIMIT_S);

  // Connect to WiFi (credentials now loaded from NVS)
  Serial.println("Connecting to WiFi...");
  while (!wifiManager.connect()) {
    printStatus("WiFi Connection", false, wifiManager.getLastError());
    retryOrSleep();
  }
  printStatus("WiFi Connection", true);
  Serial.printf("Connected to %s (IP: %s)\n", wifiManager.getSSID(), wifiManager.getIP());
  Serial.printf("WiFi RSSI: %d dBm\n", wifiManager.getRSSI());

  // Sync before TLS, which checks the MQTT server certificate dates
  Serial.println("Synchronizing time with NTP servers...");
  while (!timeManager.syncTime()) {
    printStatus("Time Sync", false, timeManager.getLastError());
    Serial.println("NTP sync failed. Cannot validate the MQTT server certificate without current time.");
    retryOrSleep();
  }
  printStatus("Time Sync", true);
  Serial.printf("Current timestamp: %lu\n", timeManager.getCurrentTimestamp());

  char timeString[32];
  if (timeManager.getFormattedTime(timeString, sizeof(timeString))) {
    Serial.printf("Current time: %s\n", timeString);
  }

  // Initialize MQTT client (certificates already loaded by FactoryIdentity)
  if (!mqttClient.begin()) {
    printStatus("MQTT Client", false, mqttClient.getLastError());
    powerManager.sleep();
  }
  printStatus("MQTT Client", true);

  // Connect to MQTT server
  Serial.println("Connecting to MQTT server...");
  if (!mqttClient.connect()) {
    printStatus("MQTT Connection", false, mqttClient.getLastError());
    // Continue anyway - will retry in loop
  } else {
    printStatus("MQTT Connection", true);
    const MqttServer server = settings.getMqttServer();
    Serial.printf("Connected to %s:%u\n", server.host, (unsigned)server.port);
  }

  Serial.println("All components initialized successfully");
  Serial.printf("Sleep duration: %lu seconds (%.1f minutes)\n", (unsigned long)settings.getInterval(),
                settings.getInterval() / 60.0);
  Serial.println("Starting main loop...\n");
}

void loop() {
  // Check WiFi connection
  if (!wifiManager.isConnected()) {
    Serial.println("WiFi disconnected, attempting to reconnect...");
    if (!wifiManager.reconnect()) {
      printStatus("WiFi Reconnect", false, wifiManager.getLastError());
      retryOrSleep();
      return;
    }
    printStatus("WiFi Reconnect", true);
    Serial.printf("Reconnected to %s (IP: %s)\n", wifiManager.getSSID(), wifiManager.getIP());
  }

  // Read sensor data
  const WeatherData data = {sensor.getTemperature(), sensor.getPressure(),  sensor.getHumidity(),
                            sensor.getAltitude(),    wifiManager.getRSSI(), timeManager.getCurrentTimestamp(),
                            settings.getLocation(),  settings.getLabel()};

  // Validate sensor readings
  if (std::isnan(data.temperature) || std::isnan(data.pressure) || std::isnan(data.humidity)) {
    Serial.println("ERROR: Sensor returned invalid readings");
    retryOrSleep(); // A glitch on a new image's first reading mustn't roll it back
    return;
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

  // Publish data to MQTT server
  Serial.println("\nPublishing data to MQTT server...");
  if (!mqttClient.publishWeatherData(data)) {
    printStatus("Data Publish", false, mqttClient.getLastError());
    if (pendingVerify) {
      mqttClient.disconnect();
      retryOrSleep();
      return;
    }
  } else {
    printStatus("Data Publish", true);
    if (pendingVerify) {
      ota.markValid();
      pendingVerify = false;
    }
    checkForUpdate();
  }

  // Disconnect from MQTT (reduces power consumption during sleep)
  mqttClient.disconnect();

  // Enter deep sleep regardless of publish status
  Serial.printf("Entering deep sleep for %lu seconds...\n", (unsigned long)settings.getInterval());
  Serial.println("=====================================\n");
  powerManager.sleep();
}
