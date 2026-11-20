#include <math.h>
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

// Global test fixtures
Preferences testPrefs;
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
  WiFi.setBeginFails(false);
  WiFi.disconnect();
}

void tearDown(void) { testPrefs.end(); }

// ========================================
// Test Cases - Factory Identity
// ========================================

void test_certificate_manager_begin_no_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);

  bool result = certMgr.begin();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(certMgr.needsProvisioning());
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(mockArduino.hasLogContaining("factory.py"));
}

void test_certificate_manager_begin_with_factory_identity(void) {
  seedIdentity();
  CertificateManager certMgr(testPrefs, &mockArduino);

  bool result = certMgr.begin();

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(certMgr.isProvisioned());
  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getCN());
  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getSensorName());
  TEST_ASSERT_EQUAL_UINT32(123456, certMgr.getPasskey());
}

void test_certificate_manager_begin_rejects_missing_passkey(void) {
  seedIdentity(VALID_CERT_PEM, CA_CERT_PEM, 0);
  CertificateManager certMgr(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(certMgr.begin());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "passkey") != NULL);
}

void test_certificate_manager_begin_rejects_out_of_range_passkey(void) {
  seedIdentity(VALID_CERT_PEM, CA_CERT_PEM, 1000000);
  CertificateManager certMgr(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(certMgr.begin());
}

void test_certificate_manager_invalid_certificate_keeps_nvs(void) {
  // The identity can't be re-created on the device, so a bad cert must never
  // wipe NVS: the next boot (or a fixed firmware) sees the same data.
  seedIdentity(INVALID_CERT);
  CertificateManager certMgr(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(certMgr.begin());
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Invalid certificate format") != NULL);
  TEST_ASSERT_TRUE(testPrefs.isKey("cli_cert"));
  TEST_ASSERT_TRUE(testPrefs.isKey("cli_key"));
}

void test_certificate_manager_validate_fails_without_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();

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
  certMgr.begin();

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
  certMgr.begin();

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
  certMgr.begin();

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
  bool saved = certMgr.applyProvisioning(ble.ssid(), ble.password(), ble.latitude(), ble.longitude(), ble.label());
  ble.notifyStatus(certMgr.getProvisioningStatus());
  return saved;
}

void test_ble_provision_valid_payload(void) {
  MockBleProvisioner ble;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);

  ble.setPayload("my-network", "my-password", 45.504f, -73.617f);

  TEST_ASSERT_TRUE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("ok", ble.lastStatus.c_str());
  TEST_ASSERT_EQUAL_STRING("my-network", wifiMgr.getSSID());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr.getLatitude());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr.getLongitude());
}

void test_ble_provision_rejects_bad_location(void) {
  MockBleProvisioner ble;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);

  const float bad[][2] = {{999.0f, -73.617f}, {45.504f, -181.0f}, {NAN, -73.617f}, {45.504f, NAN}};
  for (const auto &location : bad) {
    ble.setPayload("my-network", "my-password", location[0], location[1]);
    TEST_ASSERT_FALSE(provision(ble, certMgr));
    TEST_ASSERT_EQUAL_STRING("error:location", ble.lastStatus.c_str());
  }
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_ble_provision_rejects_empty_credentials(void) {
  MockBleProvisioner ble;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);

  ble.setPayload("", "my-password", 45.504f, -73.617f);
  TEST_ASSERT_FALSE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("error:ssid", ble.lastStatus.c_str());

  ble.setPayload("my-network", "", 45.504f, -73.617f);
  TEST_ASSERT_FALSE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("error:password", ble.lastStatus.c_str());
}

void test_ble_provision_credential_lengths(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);

  const std::string ssid32(32, 's');
  const std::string password64(64, 'a');
  TEST_ASSERT_TRUE(certMgr.applyProvisioning(ssid32.c_str(), password64.c_str(), 45.5f, -73.6f, ""));
  TEST_ASSERT_EQUAL_STRING(ssid32.c_str(), wifiMgr.getSSID());

  TEST_ASSERT_FALSE(certMgr.applyProvisioning((ssid32 + "s").c_str(), "my-password", 45.5f, -73.6f, ""));
  TEST_ASSERT_EQUAL_STRING("error:ssid", certMgr.getProvisioningStatus());
  TEST_ASSERT_FALSE(certMgr.applyProvisioning("my-network", (password64 + "a").c_str(), 45.5f, -73.6f, ""));
  TEST_ASSERT_EQUAL_STRING("error:password", certMgr.getProvisioningStatus());
  TEST_ASSERT_EQUAL_STRING(ssid32.c_str(), wifiMgr.getSSID());
}

void test_ble_provision_failed_join_saves_nothing(void) {
  seedIdentity();
  MockBleProvisioner ble;
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);
  TEST_ASSERT_TRUE(certMgr.applyProvisioning("old-network", "old-password", 45.504f, -73.617f, "Gazebo"));

  WiFi.setBeginFails(true);
  ble.setPayload("new-network", "wrong-password", 10.0f, 20.0f, "Garden");
  TEST_ASSERT_FALSE(provision(ble, certMgr));
  TEST_ASSERT_EQUAL_STRING("error:wifi", ble.lastStatus.c_str());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "timeout") != NULL);

  // The board keeps its working settings, in memory and in NVS.
  TEST_ASSERT_EQUAL_STRING("old-network", wifiMgr.getSSID());
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr.getLabel());
  CertificateManager reloaded(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(reloaded.begin());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, reloaded.getLatitude());
  TEST_ASSERT_EQUAL_STRING("Gazebo", reloaded.getLabel());

  // The client fixes the password and commits again.
  WiFi.setBeginFails(false);
  ble.setPayload("new-network", "right-password", 10.0f, 20.0f, "Garden");
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
  TEST_ASSERT_TRUE(certMgr.begin());
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);
  MockBleProvisioner ble;
  ble.begin(certMgr.getCN(), certMgr.getPasskey(), certMgr.getLabel(), certMgr.getLatitude(),
            certMgr.getLongitude());

  ble.setWiFiPayload("new-network", "my-password");

  TEST_ASSERT_TRUE(provision(ble, certMgr));
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr.getLatitude());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr.getLongitude());
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr.getLabel());
}

void test_ble_provision_rejects_failed_location_write(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);
  testPrefs.begin("tarameteo_certs", true); // read-only: every put* returns 0

  bool ok = certMgr.applyProvisioning("my-network", "my-password", 45.504f, -73.617f, "Gazebo");

  TEST_ASSERT_FALSE(ok);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Failed to store location") != NULL);
  TEST_ASSERT_EQUAL_STRING("error:storage", certMgr.getProvisioningStatus());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 0.0f, certMgr.getLatitude());
  TEST_ASSERT_TRUE(wifiMgr.needsProvisioning());
}

void test_ble_provision_location_persists_across_instances(void) {
  seedIdentity();
  {
    CertificateManager certMgr1(testPrefs, &mockArduino);
    certMgr1.begin();
    WiFiManager wifiMgr;
    certMgr1.setWiFiManager(&wifiMgr);

    TEST_ASSERT_TRUE(certMgr1.applyProvisioning("my-network", "my-password", 45.504f, -73.617f, "Gazebo"));
  }

  CertificateManager certMgr2(testPrefs, &mockArduino);
  TEST_ASSERT_TRUE(certMgr2.begin());

  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr2.getLatitude());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr2.getLongitude());
  TEST_ASSERT_EQUAL_STRING("Gazebo", certMgr2.getLabel());
}

void test_ble_provision_rejects_bad_label(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);

  const char *bad[] = {
      "Gazebo\nBcc: x@example.com",           // control character, into an email subject
      "123456789012345678901234567890123",    // 33 bytes
      "\xc3",                                 // cut-off UTF-8
      "\xed\xa0\x80",                         // surrogate
  };
  for (const char *label : bad) {
    TEST_ASSERT_FALSE_MESSAGE(certMgr.applyProvisioning("my-network", "my-password", 45.5f, -73.6f, label), label);
    TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Invalid label") != NULL);
    TEST_ASSERT_EQUAL_STRING("error:label", certMgr.getProvisioningStatus());
  }
  TEST_ASSERT_EQUAL_STRING("", certMgr.getLabel());
}

void test_ble_provision_accepts_utf8_and_empty_labels(void) {
  CertificateManager certMgr(testPrefs, &mockArduino);
  certMgr.begin();
  WiFiManager wifiMgr;
  certMgr.setWiFiManager(&wifiMgr);

  // 16 two-byte characters: 32 bytes, the most there is room for.
  TEST_ASSERT_TRUE(certMgr.applyProvisioning("my-network", "my-password", 45.5f, -73.6f,
                                             "éééééééééééééééé"));
  TEST_ASSERT_TRUE(certMgr.applyProvisioning("my-network", "my-password", 45.5f, -73.6f, "Abri 🌧"));
  TEST_ASSERT_EQUAL_STRING("Abri 🌧", certMgr.getLabel());
  TEST_ASSERT_TRUE(certMgr.applyProvisioning("my-network", "my-password", 45.5f, -73.6f, ""));
  TEST_ASSERT_EQUAL_STRING("", certMgr.getLabel());
}
void test_ble_poll_empty_when_no_payload(void) {
  MockBleProvisioner ble;
  TEST_ASSERT_FALSE(ble.poll());  // nothing staged -> nothing to consume
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
  RUN_TEST(test_ble_provision_credential_lengths);
  RUN_TEST(test_ble_provision_failed_join_saves_nothing);
  RUN_TEST(test_ble_provision_wifi_only_keeps_location_and_label);
  RUN_TEST(test_ble_provision_location_persists_across_instances);
  RUN_TEST(test_ble_provision_rejects_bad_label);
  RUN_TEST(test_ble_provision_accepts_utf8_and_empty_labels);
  RUN_TEST(test_ble_poll_empty_when_no_payload);

  return UNITY_END();
}
