#include <string.h>
#include <unity.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#include "Preferences.h"
#include "mock_arduino_core.h"
#include "mock_wifi_client.h"
#endif

#include "../../lib/Station/include/FactoryIdentity.h"

// Include implementation files for linking
#include "../../lib/Station/src/FactoryIdentity.cpp"
#include "../../lib/Station/src/X509Parser.cpp"

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
  mockArduino.reset();
  testPrefs.clear();
}

void tearDown(void) { testPrefs.end(); }

// ========================================
// Test Cases - Factory Identity
// ========================================

void test_factory_identity_begin_no_certificates(void) {
  FactoryIdentity identity(testPrefs, &mockArduino);

  bool result = identity.begin();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(identity.isLoaded());
  TEST_ASSERT_TRUE(mockArduino.hasLogContaining("factory.py"));
}

void test_factory_identity_begin_with_factory_identity(void) {
  seedIdentity();
  FactoryIdentity identity(testPrefs, &mockArduino);

  bool result = identity.begin();

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(identity.isLoaded());
  TEST_ASSERT_EQUAL_STRING("station-01", identity.getCN());
  TEST_ASSERT_EQUAL_UINT32(123456, identity.getPasskey());
}

void test_factory_identity_begin_rejects_missing_passkey(void) {
  seedIdentity(VALID_CERT_PEM, CA_CERT_PEM, 0);
  FactoryIdentity identity(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(identity.begin());
  TEST_ASSERT_TRUE(strstr(identity.getLastError(), "passkey") != NULL);
}

void test_factory_identity_begin_rejects_out_of_range_passkey(void) {
  seedIdentity(VALID_CERT_PEM, CA_CERT_PEM, 1000000);
  FactoryIdentity identity(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(identity.begin());
}

void test_factory_identity_invalid_certificate_keeps_nvs(void) {
  // The identity can't be re-created on the device, so a bad cert must never
  // wipe NVS: the next boot (or a fixed firmware) sees the same data.
  seedIdentity(INVALID_CERT);
  FactoryIdentity identity(testPrefs, &mockArduino);

  TEST_ASSERT_FALSE(identity.begin());
  TEST_ASSERT_FALSE(identity.isLoaded());
  TEST_ASSERT_TRUE(strstr(identity.getLastError(), "Invalid certificate format") != NULL);
  TEST_ASSERT_TRUE(testPrefs.isKey("cli_cert"));
  TEST_ASSERT_TRUE(testPrefs.isKey("cli_key"));
}

void test_factory_identity_validate_fails_without_certificates(void) {
  FactoryIdentity identity(testPrefs, &mockArduino);
  identity.begin();

  bool result = identity.validateCertificates();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(strstr(identity.getLastError(), "not provisioned") != NULL);
}

// ========================================
// Test Cases - Certificate Loading
// ========================================

void test_factory_identity_load_certificates_to_client(void) {
  seedIdentity();
  MockWiFiClient mockClient;
  FactoryIdentity identity(testPrefs, &mockArduino);
  identity.begin();

  bool result = identity.loadCertificates(mockClient);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(mockClient.certificateSet);
  TEST_ASSERT_TRUE(mockClient.privateKeySet);
  TEST_ASSERT_TRUE(mockClient.caCertSet);
}

void test_factory_identity_load_fails_without_ca_cert(void) {
  seedIdentity(VALID_CERT_PEM, nullptr);
  MockWiFiClient mockClient;
  FactoryIdentity identity(testPrefs, &mockArduino);
  identity.begin();

  bool result = identity.loadCertificates(mockClient);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(mockClient.certificateSet);
  TEST_ASSERT_FALSE(mockClient.privateKeySet);
  TEST_ASSERT_FALSE(mockClient.caCertSet);
  TEST_ASSERT_TRUE(strstr(identity.getLastError(), "CA certificate is required") != NULL);
}

void test_factory_identity_load_fails_without_identity(void) {
  MockWiFiClient mockClient;
  FactoryIdentity identity(testPrefs, &mockArduino);
  identity.begin();

  bool result = identity.loadCertificates(mockClient);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(mockClient.certificateSet);
}

// ========================================
// Main - Unity Test Runner
// ========================================

int main(int argc, char **argv) {
  UNITY_BEGIN();
  RUN_TEST(test_factory_identity_begin_no_certificates);
  RUN_TEST(test_factory_identity_begin_with_factory_identity);
  RUN_TEST(test_factory_identity_begin_rejects_missing_passkey);
  RUN_TEST(test_factory_identity_begin_rejects_out_of_range_passkey);
  RUN_TEST(test_factory_identity_invalid_certificate_keeps_nvs);
  RUN_TEST(test_factory_identity_validate_fails_without_certificates);
  RUN_TEST(test_factory_identity_load_certificates_to_client);
  RUN_TEST(test_factory_identity_load_fails_without_ca_cert);
  RUN_TEST(test_factory_identity_load_fails_without_identity);
  return UNITY_END();
}
