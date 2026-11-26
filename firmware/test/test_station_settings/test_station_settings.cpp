#include <math.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <unity.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#include "Preferences.h"
#include "WiFi.h"
#include "mock_arduino_core.h"
#include "mock_ble_provisioner.h"

// Override millis/delay for testing
unsigned long _mock_millis = 0;
unsigned long millis() { return _mock_millis; }
void delay(unsigned long ms) { _mock_millis += ms; }
#endif

#include "../../lib/Station/include/StationSettings.h"
#include "../../lib/WiFiManager/WiFiManager.h"

// Include implementation files for linking
#include "../../lib/Station/src/StationSettings.cpp"
#include "../../lib/WiFiManager/WiFiManager.cpp"
#include "../../test/mocks/mocks.cpp"

// config.h's defaults, which a payload sends back when the client leaves them alone.
const MqttServer DEFAULT_SERVER = {"meteo.taram.ca", 8883};
const uint32_t DEFAULT_INTERVAL = 3600;

// A network the mock WiFi joins, for tests about something else.
const WiFiCredentials HOME_WIFI = {"my-network", "my-password"};

// Elapses on the mock clock, which delay() advances.
const int WIFI_TIMEOUT_MS = 30000;

// Global test fixtures
Preferences testPrefs;
Preferences wifiPrefs; // WiFiManager's tarameteo_wifi namespace
MockArduino mockArduino;

// ========================================
// Test Setup/Teardown
// ========================================

void setUp(void) {
  _mock_millis = 0;
  mockArduino.reset();
  testPrefs.clear();
  wifiPrefs.clear();
  WiFi.setBeginFails(false);
  WiFi.disconnect();
}

void tearDown(void) {
  testPrefs.end();
  wifiPrefs.end();
}

// ========================================
// Test Cases - BLE Provisioning Transport
// ========================================
// These drive the same main-loop sequence the firmware uses (poll ->
// "provisioning" -> apply -> final status).

bool provision(MockBleProvisioner &ble, StationSettings &settings) {
  if (ble.poll() != BleRequest::Provision) {
    ble.notifyStatus("nothing committed");
    return false;
  }
  ble.notifyStatus("provisioning");
  bool saved = settings.apply(ble.wifi(), ble.location(), ble.label(), ble.mqttServer(), ble.interval(), ble.autoUpdate());
  ble.notifyStatus(settings.getStatus());
  return saved;
}

// Opens a session as main() does: the transport starts with the board's current settings.
void startSession(MockBleProvisioner &ble, const StationSettings &settings) {
  ble.begin("tm-test", 123456, settings.getLabel(), settings.getLocation(), settings.getMqttServer(),
            settings.getInterval(), settings.getAutoUpdate(), nullptr, 0);
}

void test_ble_provision_valid_payload(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  MockBleProvisioner ble;
  startSession(ble, settings);

  ble.setPayload(HOME_WIFI, {45.504f, -73.617f});

  TEST_ASSERT_TRUE(provision(ble, settings));
  TEST_ASSERT_EQUAL_STRING("ok", ble.lastStatus.c_str());
  TEST_ASSERT_EQUAL_STRING("my-network", wifiMgr.getSSID());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, settings.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, settings.getLocation().longitude);
}

void test_ble_provision_rejects_bad_location(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  MockBleProvisioner ble;
  startSession(ble, settings);

  const Location bad[] = {{999.0f, -73.617f}, {45.504f, -181.0f}, {NAN, -73.617f}, {45.504f, NAN}};
  for (const Location &location : bad) {
    ble.setPayload(HOME_WIFI, location);
    TEST_ASSERT_FALSE(provision(ble, settings));
    TEST_ASSERT_EQUAL_STRING("error:location", ble.lastStatus.c_str());
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_ble_provision_rejects_empty_credentials(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  MockBleProvisioner ble;
  startSession(ble, settings);

  ble.setPayload({"", "my-password"}, {45.504f, -73.617f});
  TEST_ASSERT_FALSE(provision(ble, settings));
  TEST_ASSERT_EQUAL_STRING("error:ssid", ble.lastStatus.c_str());

  ble.setPayload({"my-network", ""}, {45.504f, -73.617f});
  TEST_ASSERT_FALSE(provision(ble, settings));
  TEST_ASSERT_EQUAL_STRING("error:password", ble.lastStatus.c_str());
}

void test_ble_provision_credential_lengths(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);

  const std::string ssid32(32, 's');
  const std::string password64(64, 'a');
  TEST_ASSERT_TRUE(
      settings.apply({ssid32.c_str(), password64.c_str()}, {45.5f, -73.6f}, "", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  TEST_ASSERT_EQUAL_STRING(ssid32.c_str(), wifiMgr.getSSID());

  TEST_ASSERT_FALSE(
      settings.apply({(ssid32 + "s").c_str(), "my-password"}, {45.5f, -73.6f}, "", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  TEST_ASSERT_EQUAL_STRING("error:ssid", settings.getStatus());
  TEST_ASSERT_FALSE(settings.apply({"my-network", (password64 + "a").c_str()}, {45.5f, -73.6f}, "", DEFAULT_SERVER,
                                   DEFAULT_INTERVAL, true));
  TEST_ASSERT_EQUAL_STRING("error:password", settings.getStatus());
  TEST_ASSERT_EQUAL_STRING(ssid32.c_str(), wifiMgr.getSSID());
}

void test_ble_provision_failed_join_saves_nothing(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_TRUE(
      settings.apply({"old-network", "old-password"}, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  MockBleProvisioner ble;
  startSession(ble, settings);

  WiFi.setBeginFails(true);
  ble.setPayload({"new-network", "wrong-password"}, {10.0f, 20.0f}, "Garden");
  TEST_ASSERT_FALSE(provision(ble, settings));
  TEST_ASSERT_EQUAL_STRING("error:wifi", ble.lastStatus.c_str());
  TEST_ASSERT_TRUE(strstr(settings.getLastError(), "timeout") != NULL);

  // The board keeps its working settings, in memory and in NVS.
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  TEST_ASSERT_EQUAL_STRING("Gazebo", settings.getLabel());
  StationSettings reloaded(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(reloaded.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, reloaded.getLocation().latitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", reloaded.getLabel());

  // The client fixes the password and commits again.
  WiFi.setBeginFails(false);
  ble.setPayload({"new-network", "right-password"}, {10.0f, 20.0f}, "Garden");
  TEST_ASSERT_TRUE(provision(ble, settings));
  TEST_ASSERT_EQUAL_STRING("ok", ble.lastStatus.c_str());
  TEST_ASSERT_EQUAL_STRING("new-network", wifiMgr.getSSID());
}

void test_ble_provision_wifi_only_keeps_location_and_label(void) {
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putFloat("latitude", 45.504f);
  testPrefs.putFloat("longitude", -73.617f);
  testPrefs.putString("label", "Gazebo");
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  MockBleProvisioner ble;
  startSession(ble, settings);

  ble.setWiFiPayload({"new-network", "my-password"});

  TEST_ASSERT_TRUE(provision(ble, settings));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, settings.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, settings.getLocation().longitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", settings.getLabel());
}

void test_ble_provision_rejects_failed_location_write(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  testPrefs.begin("tarameteo_certs", true); // read-only: every put* returns 0

  bool ok = settings.apply(HOME_WIFI, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL, true);

  TEST_ASSERT_FALSE(ok);
  TEST_ASSERT_TRUE(strstr(settings.getLastError(), "Failed to store location") != NULL);
  TEST_ASSERT_EQUAL_STRING("error:storage", settings.getStatus());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, settings.getLocation().latitude);
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_ble_provision_rejects_failed_label_write(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  testPrefs.failWritesTo("label");

  bool ok = settings.apply(HOME_WIFI, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL, true);

  TEST_ASSERT_FALSE(ok);
  TEST_ASSERT_TRUE(strstr(settings.getLastError(), "Failed to store label") != NULL);
  TEST_ASSERT_EQUAL_STRING("error:storage", settings.getStatus());
  TEST_ASSERT_EQUAL_STRING("", settings.getLabel());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_wifi_reconnect_reports_every_attempt(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  WiFi.setBeginFails(true);

  TEST_ASSERT_FALSE(wifiMgr.reconnect());
  TEST_ASSERT_EQUAL_STRING("Failed to reconnect after 3 attempts", wifiMgr.getLastError());
}

void test_ble_provision_location_persists_across_instances(void) {
  {
    WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
    StationSettings settings1(testPrefs, &mockArduino, wifiMgr);
    settings1.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

    TEST_ASSERT_TRUE(settings1.apply(HOME_WIFI, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  }

  WiFiManager reloadedWifi(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings2(testPrefs, &mockArduino, reloadedWifi);
  TEST_ASSERT_TRUE(settings2.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));

  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, settings2.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, settings2.getLocation().longitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", settings2.getLabel());
}

void test_ble_provision_rejects_bad_label(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);

  const char *bad[] = {
      "Gazebo\nBcc: x@example.com",        // control character, into an email subject
      "123456789012345678901234567890123", // 33 bytes
      "\xc3",                              // cut-off UTF-8
      "\xed\xa0\x80",                      // surrogate
  };
  for (const char *label : bad) {
    TEST_ASSERT_FALSE_MESSAGE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, label, DEFAULT_SERVER, DEFAULT_INTERVAL, true),
                              label);
    TEST_ASSERT_TRUE(strstr(settings.getLastError(), "Invalid label") != NULL);
    TEST_ASSERT_EQUAL_STRING("error:label", settings.getStatus());
  }
  TEST_ASSERT_EQUAL_STRING("", settings.getLabel());
}

void test_ble_provision_accepts_utf8_and_empty_labels(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);

  // 16 two-byte characters: 32 bytes, the most there is room for.
  TEST_ASSERT_TRUE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "éééééééééééééééé", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  TEST_ASSERT_TRUE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "Abri 🌧", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  TEST_ASSERT_EQUAL_STRING("Abri 🌧", settings.getLabel());
  TEST_ASSERT_TRUE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "", DEFAULT_SERVER, DEFAULT_INTERVAL, true));
  TEST_ASSERT_EQUAL_STRING("", settings.getLabel());
}

// ========================================
// Test Cases - MQTT server and interval
// ========================================

void test_server_and_interval_default_until_provisioned(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin({"default.example", 1883}, 900));

  TEST_ASSERT_EQUAL_STRING("default.example", settings.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(1883, settings.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(900, settings.getInterval());
}

void test_provisioned_server_and_interval_persist(void) {
  {
    WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
    StationSettings settings(testPrefs, &mockArduino, wifiMgr);
    TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
    MockBleProvisioner ble;
    startSession(ble, settings);
    ble.setPayload(HOME_WIFI, {45.5f, -73.6f});
    ble.setServer({"192.168.1.20", 18883});
    ble.setInterval(60);

    TEST_ASSERT_TRUE(provision(ble, settings));
    TEST_ASSERT_EQUAL_STRING("192.168.1.20", settings.getMqttServer().host);
    TEST_ASSERT_EQUAL_UINT16(18883, settings.getMqttServer().port);
    TEST_ASSERT_EQUAL_UINT32(60, settings.getInterval());
  }

  // A new firmware with other defaults keeps what was provisioned.
  WiFiManager reloadedWifi(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings reloaded(testPrefs, &mockArduino, reloadedWifi);
  TEST_ASSERT_TRUE(reloaded.begin({"default.example", 1883}, 900));
  TEST_ASSERT_EQUAL_STRING("192.168.1.20", reloaded.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(18883, reloaded.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(60, reloaded.getInterval());
}

void test_wifi_only_keeps_server_and_interval(void) {
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putString("mqtt_server", "mqtt.example");
  testPrefs.putULong("mqtt_port", 8884);
  testPrefs.putULong("interval", 600);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  MockBleProvisioner ble;
  startSession(ble, settings);

  ble.setWiFiPayload({"new-network", "my-password"});

  TEST_ASSERT_TRUE(provision(ble, settings));
  TEST_ASSERT_EQUAL_STRING("mqtt.example", settings.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(8884, settings.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(600, settings.getInterval());
}

void test_rejects_bad_host(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  const std::string host254(254, 'a');

  const char *bad[] = {"", "mqtt://meteo.taram.ca", "meteo.taram.ca:8883", "my server", "météo.ca", host254.c_str()};
  for (const char *host : bad) {
    TEST_ASSERT_FALSE_MESSAGE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "", {host, 8883}, DEFAULT_INTERVAL, true), host);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("error:server", settings.getStatus(), host);
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

// 0 is also what a port of the wrong length decodes as (FieldCodec.h).
void test_rejects_port_zero(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);

  TEST_ASSERT_FALSE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "", {"meteo.taram.ca", 0}, DEFAULT_INTERVAL, true));

  TEST_ASSERT_EQUAL_STRING("error:port", settings.getStatus());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_rejects_interval_out_of_range(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);

  const uint32_t bad[] = {0, 59, 86401};
  for (uint32_t interval : bad) {
    char message[16];
    snprintf(message, sizeof(message), "%lu s", (unsigned long)interval);
    TEST_ASSERT_FALSE_MESSAGE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "", DEFAULT_SERVER, interval, true), message);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("error:interval", settings.getStatus(), message);
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_accepts_host_port_and_interval_bounds(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  const std::string host253(253, 'a');

  TEST_ASSERT_TRUE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "", {host253.c_str(), 65535}, 60, true));
  TEST_ASSERT_EQUAL_UINT32(60, settings.getInterval());

  TEST_ASSERT_TRUE(settings.apply(HOME_WIFI, {45.5f, -73.6f}, "", {"10.0.0.1", 1}, 86400, true));
  TEST_ASSERT_EQUAL_UINT32(86400, settings.getInterval());
}

void test_auto_update_is_on_until_provisioned_off(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_TRUE(settings.getAutoUpdate());
  MockBleProvisioner ble;
  startSession(ble, settings);

  ble.setPayload(HOME_WIFI, {45.5f, -73.6f});
  ble.setAutoUpdate(false);
  TEST_ASSERT_TRUE(provision(ble, settings));
  TEST_ASSERT_FALSE(settings.getAutoUpdate());

  // A later session that doesn't write AutoUpdate keeps it off.
  MockBleProvisioner next;
  startSession(next, settings);
  next.setPayload(HOME_WIFI, {45.5f, -73.6f});
  TEST_ASSERT_TRUE(provision(next, settings));
  TEST_ASSERT_FALSE(settings.getAutoUpdate());
}

// ========================================
// Test Cases - Failed writes leave NVS as it was
// ========================================

// What the board holds before the payload that fails.
void provisionOldSettings(StationSettings &settings) {
  TEST_ASSERT_TRUE(
      settings.apply({"old-network", "old-password"}, {45.504f, -73.617f}, "Gazebo", {"old.example", 8884}, 600, false));
}

void applyNewSettings(StationSettings &settings) {
  TEST_ASSERT_FALSE(
      settings.apply({"new-network", "new-password"}, {10.0f, 20.0f}, "Garden", {"new.example", 1883}, 120, true));
  TEST_ASSERT_EQUAL_STRING("error:storage", settings.getStatus());
}

// After a reboot, with other defaults, so a setting that isn't stored shows as the default.
void assertStoredSettingsAreOld(void) {
  WiFiManager reloadedWifi(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings reloaded(testPrefs, &mockArduino, reloadedWifi);
  TEST_ASSERT_TRUE(reloaded.begin({"default.example", 1}, 3600));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, reloaded.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, reloaded.getLocation().longitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", reloaded.getLabel());
  TEST_ASSERT_EQUAL_STRING("old.example", reloaded.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(8884, reloaded.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(600, reloaded.getInterval());
  TEST_ASSERT_FALSE(reloaded.getAutoUpdate());

  TEST_ASSERT_TRUE(reloadedWifi.begin());
  TEST_ASSERT_EQUAL_STRING("old-network", reloadedWifi.getSSID());
}

void assertNothingIsStored(void) {
  WiFiManager reloadedWifi(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings reloaded(testPrefs, &mockArduino, reloadedWifi);
  TEST_ASSERT_TRUE(reloaded.begin({"default.example", 1}, 3600));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, reloaded.getLocation().latitude);
  TEST_ASSERT_EQUAL_STRING("", reloaded.getLabel());
  TEST_ASSERT_EQUAL_STRING("default.example", reloaded.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(1, reloaded.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(3600, reloaded.getInterval());
  TEST_ASSERT_TRUE(reloaded.getAutoUpdate());

  TEST_ASSERT_FALSE(reloadedWifi.begin());
}

void test_failed_settings_write_keeps_the_stored_ones(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  provisionOldSettings(settings);
  testPrefs.failWritesTo("auto_update"); // The last setting, after the others are written

  applyNewSettings(settings);

  TEST_ASSERT_TRUE(strstr(settings.getLastError(), "Failed to store auto-update") != NULL);
  TEST_ASSERT_EQUAL_STRING("old.example", settings.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT32(600, settings.getInterval());
  TEST_ASSERT_FALSE(settings.getAutoUpdate());
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  assertStoredSettingsAreOld();
}

void test_failed_settings_write_on_a_new_board_stores_nothing(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  testPrefs.failWritesTo("interval");

  applyNewSettings(settings);

  TEST_ASSERT_TRUE(strstr(settings.getLastError(), "Failed to store interval") != NULL);
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
  assertNothingIsStored();
}

void test_failed_credentials_write_keeps_the_stored_settings(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  provisionOldSettings(settings);
  wifiPrefs.failWritesTo("password"); // After the settings and the SSID are written

  applyNewSettings(settings);

  TEST_ASSERT_TRUE(strstr(settings.getLastError(), "password") != NULL);
  TEST_ASSERT_EQUAL_STRING("Gazebo", settings.getLabel());
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  assertStoredSettingsAreOld();
}

void test_failed_credentials_write_on_a_new_board_stores_nothing(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  wifiPrefs.failWritesTo("password");

  applyNewSettings(settings);

  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
  assertNothingIsStored();
}

// ========================================
// Test Cases - Reset
// ========================================

// FactoryIdentity's keys, which share the namespace and must survive a reset.
void putIdentity(void) {
  testPrefs.putString("cli_cert", "CERT");
  testPrefs.putString("cli_key", "KEY");
  testPrefs.putULong("passkey", 123456);
}

void test_reset_forgets_everything_provisioning_saved(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  putIdentity();
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  provisionOldSettings(settings);
  MockBleProvisioner ble;
  startSession(ble, settings);
  ble.pending = BleRequest::Reset;

  // As main() does for a Reset commit.
  TEST_ASSERT_EQUAL(BleRequest::Reset, ble.poll());
  TEST_ASSERT_TRUE(settings.reset());
  ble.notifyStatus(settings.getStatus());

  TEST_ASSERT_EQUAL_STRING("reset", ble.lastStatus.c_str());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
  // Memory holds the defaults, like the next boot.
  TEST_ASSERT_EQUAL_STRING("", settings.getLabel());
  TEST_ASSERT_EQUAL_STRING(DEFAULT_SERVER.host, settings.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT32(DEFAULT_INTERVAL, settings.getInterval());
  TEST_ASSERT_TRUE(settings.getAutoUpdate());
  assertNothingIsStored();
}

void test_reset_keeps_the_factory_identity(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  putIdentity();
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  provisionOldSettings(settings);

  TEST_ASSERT_TRUE(settings.reset());

  char value[8];
  testPrefs.getString("cli_cert", value, sizeof(value));
  TEST_ASSERT_EQUAL_STRING("CERT", value);
  testPrefs.getString("cli_key", value, sizeof(value));
  TEST_ASSERT_EQUAL_STRING("KEY", value);
  TEST_ASSERT_EQUAL_UINT32(123456, testPrefs.getULong("passkey", 0));
}

void test_reset_of_a_new_board_succeeds(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));

  TEST_ASSERT_TRUE(settings.reset());

  TEST_ASSERT_EQUAL_STRING("reset", settings.getStatus());
  assertNothingIsStored();
}

void test_failed_reset_still_forgets_the_wifi(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  StationSettings settings(testPrefs, &mockArduino, wifiMgr);
  TEST_ASSERT_TRUE(settings.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  provisionOldSettings(settings);
  testPrefs.failWritesTo("label");

  TEST_ASSERT_FALSE(settings.reset());

  TEST_ASSERT_EQUAL_STRING("error:storage", settings.getStatus());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
  // Memory shows what is left, so a retry starts from the truth.
  TEST_ASSERT_EQUAL_STRING("Gazebo", settings.getLabel());
}

void test_unknown_commit_is_neither_provision_nor_reset(void) {
  MockBleProvisioner ble;
  ble.pending = BleRequest::Unknown;
  TEST_ASSERT_EQUAL(BleRequest::Unknown, ble.poll());
  TEST_ASSERT_EQUAL(BleRequest::None, ble.poll());
}

// ========================================
// Main - Unity Test Runner
// ========================================

int main(int argc, char **argv) {
  UNITY_BEGIN();

  // BLE provisioning transport tests
  RUN_TEST(test_ble_provision_valid_payload);
  RUN_TEST(test_ble_provision_rejects_bad_location);
  RUN_TEST(test_ble_provision_rejects_empty_credentials);
  RUN_TEST(test_ble_provision_rejects_failed_location_write);
  RUN_TEST(test_ble_provision_rejects_failed_label_write);
  RUN_TEST(test_ble_provision_credential_lengths);
  RUN_TEST(test_ble_provision_failed_join_saves_nothing);
  RUN_TEST(test_ble_provision_wifi_only_keeps_location_and_label);
  RUN_TEST(test_ble_provision_location_persists_across_instances);
  RUN_TEST(test_ble_provision_rejects_bad_label);
  RUN_TEST(test_ble_provision_accepts_utf8_and_empty_labels);

  // MQTT server and interval tests
  RUN_TEST(test_server_and_interval_default_until_provisioned);
  RUN_TEST(test_provisioned_server_and_interval_persist);
  RUN_TEST(test_wifi_only_keeps_server_and_interval);
  RUN_TEST(test_rejects_bad_host);
  RUN_TEST(test_rejects_port_zero);
  RUN_TEST(test_rejects_interval_out_of_range);
  RUN_TEST(test_accepts_host_port_and_interval_bounds);

  // Failed write tests
  RUN_TEST(test_failed_settings_write_keeps_the_stored_ones);
  RUN_TEST(test_failed_settings_write_on_a_new_board_stores_nothing);
  RUN_TEST(test_failed_credentials_write_keeps_the_stored_settings);
  RUN_TEST(test_failed_credentials_write_on_a_new_board_stores_nothing);

  // WiFi manager tests
  RUN_TEST(test_wifi_reconnect_reports_every_attempt);

  // Reset tests
  RUN_TEST(test_reset_forgets_everything_provisioning_saved);
  RUN_TEST(test_reset_keeps_the_factory_identity);
  RUN_TEST(test_reset_of_a_new_board_succeeds);
  RUN_TEST(test_failed_reset_still_forgets_the_wifi);
  RUN_TEST(test_unknown_commit_is_neither_provision_nor_reset);
  RUN_TEST(test_auto_update_is_on_until_provisioned_off);

  return UNITY_END();
}
