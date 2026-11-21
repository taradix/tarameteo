#include <math.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <unity.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#include "Preferences.h"
#include "WiFi.h"
#include "./mocks/mock_arduino_core.h"
#include "./mocks/mock_ble_provisioner.h"
#include "./mocks/mock_wifi_client.h"

// Override millis/delay for testing
unsigned long _mock_millis = 0;
unsigned long millis() { return _mock_millis; }
void delay(unsigned long ms) { _mock_millis += ms; }
#endif

#include "../../lib/CertificateManager/include/CertificateManager.h"
#include "../../lib/WiFiManager/WiFiManager.h"

// Include implementation files for linking
#include "../../lib/CertificateManager/src/CertificateManager.cpp"
#include "../../lib/CertificateManager/src/X509Parser.cpp"
#include "../../lib/WiFiManager/WiFiManager.cpp"
#include "../../test/mocks/mocks.cpp"

// Test data - valid PEM certificate
const char *VALID_CERT_PEM = "-----BEGIN CERTIFICATE-----\n"
                             "MIIDXTCCAkWgAwIBAgIJAKL0UG+mRCQzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV\n"
                             "BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX\n"
                             "aWRnaXRzIFB0eSBMdGQwHhcNMjQwMTAxMDAwMDAwWhcNMzQwMTAxMDAwMDAwWjBF\n"
                             "MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50\n"
                             "ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB\n"
                             "CgKCAQEAwU4qD3z9/CN=station-01\n"
                             "-----END CERTIFICATE-----\n";

const char *VALID_KEY_PEM = "-----BEGIN PRIVATE KEY-----\n"
                            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDBTioPfP38I3oH\n"
                            "-----END PRIVATE KEY-----\n";

const char *CA_CERT_PEM = "-----BEGIN CERTIFICATE-----\n"
                          "MIIDXTCCAkWgAwIBAgIJAKL0UG+mRCQzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV\n"
                          "-----END CERTIFICATE-----\n";

const char *INVALID_CERT = "This is not a certificate";

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

// What scripts/factory.py writes into the tarameteo_certs namespace.
void seedIdentity(const char *certPem = VALID_CERT_PEM, const char *caCertPem = CA_CERT_PEM,
                  unsigned long passkey = 123456) {
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putString("cli_cert", certPem);
  testPrefs.putString("cli_key", VALID_KEY_PEM);
  if (caCertPem) {
    testPrefs.putString("ca_cert", caCertPem);
  }
  if (passkey) {
    testPrefs.putULong("passkey", passkey);
  }
  testPrefs.end();
}

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
// Test Cases - Factory Identity
// ========================================

void test_certificate_manager_begin_no_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);

  bool result = certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(certMgr.needsProvisioning());
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(mockArduino.hasLogContaining("factory.py"));
}

void test_certificate_manager_begin_with_factory_identity(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);

  bool result = certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(certMgr.isProvisioned());
  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getCN());
  TEST_ASSERT_EQUAL_UINT32(123456, certMgr.getPasskey());
}

void test_certificate_manager_begin_rejects_missing_passkey(void) {
  seedIdentity(VALID_CERT_PEM, CA_CERT_PEM, 0);
  CertificateManager certMgr(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "passkey") != NULL);
}

void test_certificate_manager_begin_rejects_out_of_range_passkey(void) {
  seedIdentity(VALID_CERT_PEM, CA_CERT_PEM, 1000000);
  CertificateManager certMgr(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
}

void test_certificate_manager_invalid_certificate_keeps_nvs(void) {
  // The identity can't be re-created on the device, so a bad cert must never
  // wipe NVS: the next boot (or a fixed firmware) sees the same data.
  seedIdentity(INVALID_CERT);
  CertificateManager certMgr(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Invalid certificate format") != NULL);
  TEST_ASSERT_TRUE(testPrefs.isKey("cli_cert"));
  TEST_ASSERT_TRUE(testPrefs.isKey("cli_key"));
}

void test_certificate_manager_validate_fails_without_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

  bool result = certMgr.validateCertificates();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "not provisioned") != NULL);
}

// ========================================
// Test Cases - Certificate Loading
// ========================================

void test_certificate_manager_load_certificates_to_client(void) {
  seedIdentity();
  MockWiFiClient mockClient;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

  bool result = certMgr.loadCertificates(mockClient);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(mockClient.certificateSet);
  TEST_ASSERT_TRUE(mockClient.privateKeySet);
  TEST_ASSERT_TRUE(mockClient.caCertSet);
}

void test_certificate_manager_load_fails_without_ca_cert(void) {
  seedIdentity(VALID_CERT_PEM, nullptr);
  MockWiFiClient mockClient;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

  bool result = certMgr.loadCertificates(mockClient);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(mockClient.certificateSet);
  TEST_ASSERT_FALSE(mockClient.privateKeySet);
  TEST_ASSERT_FALSE(mockClient.caCertSet);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "CA certificate is required") != NULL);
}

void test_certificate_manager_load_fails_without_provisioning(void) {
  MockWiFiClient mockClient;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);

  bool result = certMgr.loadCertificates(mockClient);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(mockClient.certificateSet);
}

// ========================================
// Test Cases - BLE Provisioning Transport
// ========================================
// These drive the same main-loop sequence the firmware uses (poll ->
// "provisioning" -> applyProvisioning -> final status).

bool provision(MockBleProvisioner &ble, CertificateManager &certMgr) {
  if (!ble.poll()) {
    ble.notifyStatus("nothing committed");
    return false;
  }
  ble.notifyStatus("provisioning");
  bool saved = certMgr.applyProvisioning(ble.wifi(), ble.location(), ble.label(), ble.mqttServer(), ble.interval());
  ble.notifyStatus(certMgr.getProvisioningStatus());
  return saved;
}

// Opens a session as main() does: the transport starts with the board's current settings.
void startSession(MockBleProvisioner &ble, const CertificateManager &certMgr) {
  ble.begin(certMgr.getCN(), certMgr.getPasskey(), certMgr.getLabel(), certMgr.getLocation(), certMgr.getMqttServer(),
            certMgr.getInterval(), nullptr, 0);
}

void test_ble_provision_valid_payload(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  MockBleProvisioner ble;
  startSession(ble, certMgr);

  ble.setPayload(HOME_WIFI, {45.504f, -73.617f});

  TEST_ASSERT_TRUE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("ok", ble.lastStatus.c_str());
  TEST_ASSERT_EQUAL_STRING("my-network", wifiMgr.getSSID());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr.getLocation().longitude);
}

void test_ble_provision_rejects_bad_location(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  MockBleProvisioner ble;
  startSession(ble, certMgr);

  const Location bad[] = {{999.0f, -73.617f}, {45.504f, -181.0f}, {NAN, -73.617f}, {45.504f, NAN}};
  for (const Location &location : bad) {
    ble.setPayload(HOME_WIFI, location);
    TEST_ASSERT_FALSE(provision(ble, certMgr));
    TEST_ASSERT_EQUAL_STRING("error:location", ble.lastStatus.c_str());
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_ble_provision_rejects_empty_credentials(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  MockBleProvisioner ble;
  startSession(ble, certMgr);

  ble.setPayload({"", "my-password"}, {45.504f, -73.617f});
  TEST_ASSERT_FALSE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("error:ssid", ble.lastStatus.c_str());

  ble.setPayload({"my-network", ""}, {45.504f, -73.617f});
  TEST_ASSERT_FALSE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("error:password", ble.lastStatus.c_str());
}

void test_ble_provision_credential_lengths(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);

  const std::string ssid32(32, 's');
  const std::string password64(64, 'a');
  TEST_ASSERT_TRUE(certMgr.applyProvisioning({ssid32.c_str(), password64.c_str()}, {45.5f, -73.6f}, "", DEFAULT_SERVER,
                                             DEFAULT_INTERVAL));
  TEST_ASSERT_EQUAL_STRING(ssid32.c_str(), wifiMgr.getSSID());

  TEST_ASSERT_FALSE(certMgr.applyProvisioning({(ssid32 + "s").c_str(), "my-password"}, {45.5f, -73.6f}, "",
                                              DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_EQUAL_STRING("error:ssid", certMgr.getProvisioningStatus());
  TEST_ASSERT_FALSE(certMgr.applyProvisioning({"my-network", (password64 + "a").c_str()}, {45.5f, -73.6f}, "",
                                              DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_EQUAL_STRING("error:password", certMgr.getProvisioningStatus());
  TEST_ASSERT_EQUAL_STRING(ssid32.c_str(), wifiMgr.getSSID());
}

void test_ble_provision_failed_join_saves_nothing(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  TEST_ASSERT_TRUE(certMgr.applyProvisioning({"old-network", "old-password"}, {45.504f, -73.617f}, "Gazebo",
                                             DEFAULT_SERVER, DEFAULT_INTERVAL));
  MockBleProvisioner ble;
  startSession(ble, certMgr);

  WiFi.setBeginFails(true);
  ble.setPayload({"new-network", "wrong-password"}, {10.0f, 20.0f}, "Garden");
  TEST_ASSERT_FALSE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("error:wifi", ble.lastStatus.c_str());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "timeout") != NULL);

  // The board keeps its working settings, in memory and in NVS.
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr.getLabel());
  CertificateManager reloaded(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(reloaded.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, reloaded.getLocation().latitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", reloaded.getLabel());

  // The client fixes the password and commits again.
  WiFi.setBeginFails(false);
  ble.setPayload({"new-network", "right-password"}, {10.0f, 20.0f}, "Garden");
  TEST_ASSERT_TRUE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("ok", ble.lastStatus.c_str());
  TEST_ASSERT_EQUAL_STRING("new-network", wifiMgr.getSSID());
}

void test_ble_provision_wifi_only_keeps_location_and_label(void) {
  seedIdentity();
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putFloat("latitude", 45.504f);
  testPrefs.putFloat("longitude", -73.617f);
  testPrefs.putString("label", "Gazebo");
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  MockBleProvisioner ble;
  startSession(ble, certMgr);

  ble.setWiFiPayload({"new-network", "my-password"});

  TEST_ASSERT_TRUE(provision(ble, certMgr));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr.getLocation().longitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr.getLabel());
}

void test_ble_provision_rejects_failed_location_write(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  testPrefs.begin("tarameteo_certs", true); // read-only: every put* returns 0

  bool ok = certMgr.applyProvisioning(HOME_WIFI, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL);

  TEST_ASSERT_FALSE(ok);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Failed to store location") != NULL);
  TEST_ASSERT_EQUAL_STRING("error:storage", certMgr.getProvisioningStatus());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, certMgr.getLocation().latitude);
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_ble_provision_rejects_failed_label_write(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  testPrefs.failWritesTo("label");

  bool ok = certMgr.applyProvisioning(HOME_WIFI, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL);

  TEST_ASSERT_FALSE(ok);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Failed to store label") != NULL);
  TEST_ASSERT_EQUAL_STRING("error:storage", certMgr.getProvisioningStatus());
  TEST_ASSERT_EQUAL_STRING("", certMgr.getLabel());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_wifi_reconnect_reports_every_attempt(void) {
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  WiFi.setBeginFails(true);

  TEST_ASSERT_FALSE(wifiMgr.reconnect());
  TEST_ASSERT_EQUAL_STRING("Failed to reconnect after 3 attempts", wifiMgr.getLastError());
}

void test_ble_provision_location_persists_across_instances(void) {
  seedIdentity();
  {
    CertificateManager certMgr1(testPrefs, &mockArduino);
    certMgr1.begin(DEFAULT_SERVER, DEFAULT_INTERVAL);
    WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
    certMgr1.setWiFiManager(&wifiMgr);

    TEST_ASSERT_TRUE(
        certMgr1.applyProvisioning(HOME_WIFI, {45.504f, -73.617f}, "Gazebo", DEFAULT_SERVER, DEFAULT_INTERVAL));
  }

  CertificateManager certMgr2(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr2.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));

  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr2.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr2.getLocation().longitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr2.getLabel());
}

void test_ble_provision_rejects_bad_label(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);

  const char *bad[] = {
      "Gazebo\nBcc: x@example.com",           // control character, into an email subject
      "123456789012345678901234567890123",    // 33 bytes
      "\xc3",                                 // cut-off UTF-8
      "\xed\xa0\x80",                         // surrogate
  };
  for (const char *label : bad) {
    TEST_ASSERT_FALSE_MESSAGE(
        certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, label, DEFAULT_SERVER, DEFAULT_INTERVAL), label);
    TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Invalid label") != NULL);
    TEST_ASSERT_EQUAL_STRING("error:label", certMgr.getProvisioningStatus());
  }
  TEST_ASSERT_EQUAL_STRING("", certMgr.getLabel());
}

void test_ble_provision_accepts_utf8_and_empty_labels(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);

  // 16 two-byte characters: 32 bytes, the most there is room for.
  TEST_ASSERT_TRUE(
      certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "éééééééééééééééé", DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_TRUE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "Abri 🌧", DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_EQUAL_STRING("Abri 🌧", certMgr.getLabel());
  TEST_ASSERT_TRUE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "", DEFAULT_SERVER, DEFAULT_INTERVAL));
  TEST_ASSERT_EQUAL_STRING("", certMgr.getLabel());
}

// ========================================
// Test Cases - MQTT server and interval
// ========================================

void test_server_and_interval_default_until_provisioned(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin({"default.example", 1883}, 900));

  TEST_ASSERT_EQUAL_STRING("default.example", certMgr.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(1883, certMgr.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(900, certMgr.getInterval());
}

void test_provisioned_server_and_interval_persist(void) {
  seedIdentity();
  {
    CertificateManager certMgr(testPrefs, &mockArduino);
    TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
    WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
    certMgr.setWiFiManager(&wifiMgr);
    MockBleProvisioner ble;
    startSession(ble, certMgr);
    ble.setPayload(HOME_WIFI, {45.5f, -73.6f});
    ble.setServer({"192.168.1.20", 18883});
    ble.setInterval(60);

    TEST_ASSERT_TRUE(provision(ble, certMgr));
    TEST_ASSERT_EQUAL_STRING("192.168.1.20", certMgr.getMqttServer().host);
    TEST_ASSERT_EQUAL_UINT16(18883, certMgr.getMqttServer().port);
    TEST_ASSERT_EQUAL_UINT32(60, certMgr.getInterval());
  }

  // A new firmware with other defaults keeps what was provisioned.
  CertificateManager reloaded(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(reloaded.begin({"default.example", 1883}, 900));
  TEST_ASSERT_EQUAL_STRING("192.168.1.20", reloaded.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(18883, reloaded.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(60, reloaded.getInterval());
}

void test_wifi_only_keeps_server_and_interval(void) {
  seedIdentity();
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putString("mqtt_server", "mqtt.example");
  testPrefs.putULong("mqtt_port", 8884);
  testPrefs.putULong("interval", 600);
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  MockBleProvisioner ble;
  startSession(ble, certMgr);

  ble.setWiFiPayload({"new-network", "my-password"});

  TEST_ASSERT_TRUE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("mqtt.example", certMgr.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(8884, certMgr.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(600, certMgr.getInterval());
}

void test_rejects_bad_host(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  const std::string host254(254, 'a');

  const char *bad[] = {"", "mqtt://meteo.taram.ca", "meteo.taram.ca:8883", "my server", "météo.ca", host254.c_str()};
  for (const char *host : bad) {
    TEST_ASSERT_FALSE_MESSAGE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "", {host, 8883}, DEFAULT_INTERVAL),
                              host);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("error:server", certMgr.getProvisioningStatus(), host);
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

// 0 is also what a port of the wrong length decodes as (FieldCodec.h).
void test_rejects_port_zero(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);

  TEST_ASSERT_FALSE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "", {"meteo.taram.ca", 0}, DEFAULT_INTERVAL));

  TEST_ASSERT_EQUAL_STRING("error:port", certMgr.getProvisioningStatus());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_rejects_interval_out_of_range(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);

  const uint32_t bad[] = {0, 59, 86401};
  for (uint32_t interval : bad) {
    char message[16];
    snprintf(message, sizeof(message), "%lu s", (unsigned long)interval);
    TEST_ASSERT_FALSE_MESSAGE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "", DEFAULT_SERVER, interval),
                              message);
    TEST_ASSERT_EQUAL_STRING_MESSAGE("error:interval", certMgr.getProvisioningStatus(), message);
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_accepts_host_port_and_interval_bounds(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  const std::string host253(253, 'a');

  TEST_ASSERT_TRUE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "", {host253.c_str(), 65535}, 60));
  TEST_ASSERT_EQUAL_UINT32(60, certMgr.getInterval());

  TEST_ASSERT_TRUE(certMgr.applyProvisioning(HOME_WIFI, {45.5f, -73.6f}, "", {"10.0.0.1", 1}, 86400));
  TEST_ASSERT_EQUAL_UINT32(86400, certMgr.getInterval());
}

// ========================================
// Test Cases - Failed writes leave NVS as it was
// ========================================

// What the board holds before the payload that fails.
void provisionOldSettings(CertificateManager &certMgr) {
  TEST_ASSERT_TRUE(certMgr.applyProvisioning({"old-network", "old-password"}, {45.504f, -73.617f}, "Gazebo",
                                             {"old.example", 8884}, 600));
}

void applyNewSettings(CertificateManager &certMgr) {
  TEST_ASSERT_FALSE(
      certMgr.applyProvisioning({"new-network", "new-password"}, {10.0f, 20.0f}, "Garden", {"new.example", 1883}, 120));
  TEST_ASSERT_EQUAL_STRING("error:storage", certMgr.getProvisioningStatus());
}

// After a reboot, with other defaults, so a setting that isn't stored shows as the default.
void assertStoredSettingsAreOld(void) {
  CertificateManager reloaded(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(reloaded.begin({"default.example", 1}, 3600));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, reloaded.getLocation().latitude);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, reloaded.getLocation().longitude);
  TEST_ASSERT_EQUAL_STRING("Gazebo", reloaded.getLabel());
  TEST_ASSERT_EQUAL_STRING("old.example", reloaded.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(8884, reloaded.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(600, reloaded.getInterval());

  WiFiManager reloadedWifi(wifiPrefs, WIFI_TIMEOUT_MS);
  TEST_ASSERT_TRUE(reloadedWifi.begin());
  TEST_ASSERT_EQUAL_STRING("old-network", reloadedWifi.getSSID());
}

void assertNothingIsStored(void) {
  CertificateManager reloaded(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(reloaded.begin({"default.example", 1}, 3600));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, reloaded.getLocation().latitude);
  TEST_ASSERT_EQUAL_STRING("", reloaded.getLabel());
  TEST_ASSERT_EQUAL_STRING("default.example", reloaded.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT16(1, reloaded.getMqttServer().port);
  TEST_ASSERT_EQUAL_UINT32(3600, reloaded.getInterval());

  WiFiManager reloadedWifi(wifiPrefs, WIFI_TIMEOUT_MS);
  TEST_ASSERT_FALSE(reloadedWifi.begin());
}

void test_failed_settings_write_keeps_the_stored_ones(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  provisionOldSettings(certMgr);
  testPrefs.failWritesTo("interval"); // The last setting, after the others are written

  applyNewSettings(certMgr);

  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Failed to store interval") != NULL);
  TEST_ASSERT_EQUAL_STRING("old.example", certMgr.getMqttServer().host);
  TEST_ASSERT_EQUAL_UINT32(600, certMgr.getInterval());
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  assertStoredSettingsAreOld();
}

void test_failed_settings_write_on_a_new_board_stores_nothing(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  testPrefs.failWritesTo("interval");

  applyNewSettings(certMgr);

  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
  assertNothingIsStored();
}

void test_failed_credentials_write_keeps_the_stored_settings(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  provisionOldSettings(certMgr);
  wifiPrefs.failWritesTo("password"); // After the settings and the SSID are written

  applyNewSettings(certMgr);

  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "password") != NULL);
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr.getLabel());
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  assertStoredSettingsAreOld();
}

void test_failed_credentials_write_on_a_new_board_stores_nothing(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr.begin(DEFAULT_SERVER, DEFAULT_INTERVAL));
  WiFiManager wifiMgr(wifiPrefs, WIFI_TIMEOUT_MS);
  certMgr.setWiFiManager(&wifiMgr);
  wifiPrefs.failWritesTo("password");

  applyNewSettings(certMgr);

  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
  assertNothingIsStored();
}

// ========================================
// Main - Unity Test Runner
// ========================================

int main(int argc, char **argv) {
  UNITY_BEGIN();

  // Factory identity tests
  RUN_TEST(test_certificate_manager_begin_no_certificates);
  RUN_TEST(test_certificate_manager_begin_with_factory_identity);
  RUN_TEST(test_certificate_manager_begin_rejects_missing_passkey);
  RUN_TEST(test_certificate_manager_begin_rejects_out_of_range_passkey);
  RUN_TEST(test_certificate_manager_invalid_certificate_keeps_nvs);
  RUN_TEST(test_certificate_manager_validate_fails_without_certificates);

  // Certificate loading tests
  RUN_TEST(test_certificate_manager_load_certificates_to_client);
  RUN_TEST(test_certificate_manager_load_fails_without_ca_cert);
  RUN_TEST(test_certificate_manager_load_fails_without_provisioning);

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

  return UNITY_END();
}
