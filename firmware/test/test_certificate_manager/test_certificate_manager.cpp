#include <string.h>
#include <unity.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#include "Preferences.h"
#include "./mocks/mock_arduino_core.h"
#include "./mocks/mock_web_server.h"
#include "./mocks/mock_wifi.h"
#include "./mocks/mock_wifi_client.h"

// Override millis/delay for testing
unsigned long _mock_millis = 0;
unsigned long millis() { return _mock_millis; }
void delay(unsigned long ms) { _mock_millis += ms; }
#endif

#include "../../lib/CertificateManager/include/CertificateManager.h"

// Include implementation files for linking
#include "../../lib/CertificateManager/src/CertificateManager.cpp"
#include "../../lib/CertificateManager/src/X509Parser.cpp"
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
MockWiFi mockWiFi;
MockArduino mockArduino;

// ========================================
// Test Setup/Teardown
// ========================================

void setUp(void) {
  _mock_millis = 0;
  mockWiFi.reset();
  mockArduino.reset();
  testPrefs.clear();
}

void tearDown(void) { testPrefs.end(); }

// ========================================
// Test Cases - Basic Lifecycle
// ========================================

void test_certificate_manager_begin_no_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);

  bool result = certMgr.begin();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(certMgr.needsProvisioning());
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(mockArduino.hasLogContaining("Initializing"));
}

void test_certificate_manager_begin_with_valid_certificates(void) {
  // Pre-populate NVS with valid certificates
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putString("cli_cert", VALID_CERT_PEM);
  testPrefs.putString("cli_key", VALID_KEY_PEM);
  testPrefs.putString("cert_cn", "station-01");
  testPrefs.putULong("cert_expires", 2000000000UL);
  testPrefs.putInt("cert_version", 1);
  testPrefs.end();

  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);

  bool result = certMgr.begin();

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(certMgr.isProvisioned());
  TEST_ASSERT_FALSE(certMgr.needsProvisioning());
  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getCN());
}

// ========================================
// Test Cases - Certificate Storage
// ========================================

void test_certificate_manager_store_valid_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM, CA_CERT_PEM);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(certMgr.isProvisioned());
  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getCN());
  TEST_ASSERT_EQUAL(1, certMgr.getCertificateVersion());
  TEST_ASSERT_TRUE(mockArduino.hasLogContaining("stored successfully"));
}

void test_certificate_manager_store_without_ca_cert(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(certMgr.isProvisioned());
}

void test_certificate_manager_reject_invalid_certificate(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.storeCertificates(INVALID_CERT, VALID_KEY_PEM);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Invalid certificate format") != NULL);
}

void test_certificate_manager_reject_invalid_key(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.storeCertificates(VALID_CERT_PEM, INVALID_CERT);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Invalid private key format") != NULL);
}

void test_certificate_manager_increment_version_on_store(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);
  int version1 = certMgr.getCertificateVersion();

  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);
  int version2 = certMgr.getCertificateVersion();

  TEST_ASSERT_EQUAL(1, version1);
  TEST_ASSERT_EQUAL(2, version2);
}

// ========================================
// Test Cases - Certificate Validation
// ========================================

void test_certificate_manager_validate_after_store(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);

  bool result = certMgr.validateCertificates();

  TEST_ASSERT_TRUE(result);
}

void test_certificate_manager_validate_fails_without_certificates(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.validateCertificates();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "not provisioned") != NULL);
}

void test_certificate_manager_detect_expiration_warning(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  // Set epoch time to simulate certificate expiring in 15 days
  mockArduino.setCurrentEpochSeconds(1700000000UL);

  // Pre-populate with cert expiring soon
  testPrefs.begin("tarameteo_certs", false);
  testPrefs.putString("cli_cert", VALID_CERT_PEM);
  testPrefs.putString("cli_key", VALID_KEY_PEM);
  testPrefs.putULong("cert_expires", 1700000000UL + (15 * 24 * 60 * 60)); // 15 days from now
  testPrefs.end();

  CertificateManager certMgr2(testPrefs, &mockWiFi, &mockArduino);
  certMgr2.begin();
  certMgr2.validateCertificates();

  TEST_ASSERT_TRUE(mockArduino.hasLogContaining("expires in"));
}

void test_certificate_manager_validate_fails_when_current_time_unavailable(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);

  mockArduino.setCurrentEpochSeconds(0);

  bool result = certMgr.validateCertificates();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "Current time unavailable") != NULL);
}

// ========================================
// Test Cases - Certificate Loading
// ========================================

void test_certificate_manager_load_certificates_to_client(void) {
  MockWiFiClient mockClient;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM, CA_CERT_PEM);

  bool result = certMgr.loadCertificates(mockClient);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(mockClient.certificateSet);
  TEST_ASSERT_TRUE(mockClient.privateKeySet);
  TEST_ASSERT_TRUE(mockClient.caCertSet);
}

void test_certificate_manager_load_fails_without_ca_cert(void) {
  MockWiFiClient mockClient;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);

  bool result = certMgr.loadCertificates(mockClient);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(mockClient.certificateSet);
  TEST_ASSERT_FALSE(mockClient.privateKeySet);
  TEST_ASSERT_FALSE(mockClient.caCertSet);
  TEST_ASSERT_TRUE(strstr(certMgr.getLastError(), "CA certificate is required") != NULL);
}

void test_certificate_manager_load_fails_without_provisioning(void) {
  MockWiFiClient mockClient;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.loadCertificates(mockClient);

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(mockClient.certificateSet);
}

// ========================================
// Test Cases - Certificate Clearing
// ========================================

void test_certificate_manager_clear_removes_all_data(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);

  bool result = certMgr.clearCertificates();

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
  TEST_ASSERT_EQUAL_STRING("", certMgr.getCN());
  TEST_ASSERT_EQUAL(0, certMgr.getExpirationTime());
  TEST_ASSERT_EQUAL(0, certMgr.getCertificateVersion());
}

void test_certificate_manager_clear_clears_nvs(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);
  certMgr.clearCertificates();

  // Try to create a new instance - should not find certificates
  CertificateManager certMgr2(testPrefs, &mockWiFi, &mockArduino);
  bool result = certMgr2.begin();

  TEST_ASSERT_FALSE(result);
  TEST_ASSERT_FALSE(certMgr2.isProvisioned());
}

// ========================================
// Test Cases - Provisioning Mode
// ========================================

void test_certificate_manager_start_provisioning_mode(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();

  bool result = certMgr.startProvisioningMode(&mockServer);

  TEST_ASSERT_TRUE(result);
  TEST_ASSERT_TRUE(certMgr.isProvisioningActive());
  TEST_ASSERT_TRUE(mockWiFi.disconnectCalled);
  TEST_ASSERT_TRUE(mockWiFi.apMode);
  TEST_ASSERT_TRUE(mockWiFi.apStarted);
  TEST_ASSERT_TRUE(mockServer.beginCalled);
}

void test_certificate_manager_stop_provisioning_mode(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.startProvisioningMode(&mockServer);

  certMgr.stopProvisioningMode();

  TEST_ASSERT_FALSE(certMgr.isProvisioningActive());
  TEST_ASSERT_TRUE(mockServer.stopCalled);
}

void test_certificate_manager_provisioning_loop(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.startProvisioningMode(&mockServer);

  certMgr.handleProvisioningLoop();

  TEST_ASSERT_GREATER_THAN(0, mockServer.handleClientCallCount);
}

void test_certificate_manager_provision_request_with_valid_certs(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.startProvisioningMode(&mockServer);

  mockServer.setArg("cert", VALID_CERT_PEM);
  mockServer.setArg("key", VALID_KEY_PEM);
  mockServer.setArg("latitude", "45.504");
  mockServer.setArg("longitude", "-73.617");
  mockServer.triggerHandler("/provision");

  TEST_ASSERT_EQUAL(200, mockServer.lastResponseCode);
  TEST_ASSERT_TRUE(certMgr.isProvisioned());
}

void test_certificate_manager_provision_request_missing_fields(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.startProvisioningMode(&mockServer);

  // Missing cert
  mockServer.setArg("key", VALID_KEY_PEM);
  mockServer.triggerHandler("/provision");

  TEST_ASSERT_EQUAL(400, mockServer.lastResponseCode);
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
}

void test_certificate_manager_provision_request_missing_location(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.startProvisioningMode(&mockServer);

  // Missing latitude and longitude
  mockServer.setArg("cert", VALID_CERT_PEM);
  mockServer.setArg("key", VALID_KEY_PEM);
  mockServer.triggerHandler("/provision");

  TEST_ASSERT_EQUAL(400, mockServer.lastResponseCode);
  TEST_ASSERT_FALSE(certMgr.isProvisioned());
}

void test_certificate_manager_provision_stores_location(void) {
  MockWebServer mockServer;
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.startProvisioningMode(&mockServer);

  mockServer.setArg("cert", VALID_CERT_PEM);
  mockServer.setArg("key", VALID_KEY_PEM);
  mockServer.setArg("latitude", "45.504");
  mockServer.setArg("longitude", "-73.617");
  mockServer.triggerHandler("/provision");

  TEST_ASSERT_EQUAL(200, mockServer.lastResponseCode);
  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr.getLatitude());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr.getLongitude());
}

void test_certificate_manager_location_persists_across_instances(void) {
  {
    MockWebServer mockServer;
    CertificateManager certMgr1(testPrefs, &mockWiFi, &mockArduino);
    certMgr1.begin();
    certMgr1.startProvisioningMode(&mockServer);
    mockServer.setArg("cert", VALID_CERT_PEM);
    mockServer.setArg("key", VALID_KEY_PEM);
    mockServer.setArg("latitude", "45.504");
    mockServer.setArg("longitude", "-73.617");
    mockServer.triggerHandler("/provision");
  }

  CertificateManager certMgr2(testPrefs, &mockWiFi, &mockArduino);
  certMgr2.begin();

  TEST_ASSERT_FLOAT_WITHIN(0.001f, 45.504f, certMgr2.getLatitude());
  TEST_ASSERT_FLOAT_WITHIN(0.001f, -73.617f, certMgr2.getLongitude());
}

// ========================================
// Test Cases - CN Extraction
// ========================================

void test_certificate_manager_extract_cn_from_certificate(void) {
  CertificateManager certMgr(testPrefs, &mockWiFi, &mockArduino);
  certMgr.begin();
  certMgr.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);

  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getCN());
  TEST_ASSERT_EQUAL_STRING("station-01", certMgr.getSensorName());
}

// ========================================
// Test Cases - Persistence
// ========================================

void test_certificate_manager_persistence_across_instances(void) {
  // First instance stores certificates
  {
    CertificateManager certMgr1(testPrefs, &mockWiFi, &mockArduino);
    certMgr1.begin();
    certMgr1.storeCertificates(VALID_CERT_PEM, VALID_KEY_PEM);
  }

  // Second instance should load them from NVS
  {
    CertificateManager certMgr2(testPrefs, &mockWiFi, &mockArduino);
    bool result = certMgr2.begin();

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_TRUE(certMgr2.isProvisioned());
    TEST_ASSERT_EQUAL_STRING("station-01", certMgr2.getCN());
  }
}

// ========================================
// Main - Unity Test Runner
// ========================================

int main(int argc, char **argv) {
  UNITY_BEGIN();

  // Basic lifecycle tests
  RUN_TEST(test_certificate_manager_begin_no_certificates);
  RUN_TEST(test_certificate_manager_begin_with_valid_certificates);

  // Certificate storage tests
  RUN_TEST(test_certificate_manager_store_valid_certificates);
  RUN_TEST(test_certificate_manager_store_without_ca_cert);
  RUN_TEST(test_certificate_manager_reject_invalid_certificate);
  RUN_TEST(test_certificate_manager_reject_invalid_key);
  RUN_TEST(test_certificate_manager_increment_version_on_store);

  // Certificate validation tests
  RUN_TEST(test_certificate_manager_validate_after_store);
  RUN_TEST(test_certificate_manager_validate_fails_without_certificates);
  RUN_TEST(test_certificate_manager_detect_expiration_warning);
  RUN_TEST(test_certificate_manager_validate_fails_when_current_time_unavailable);

  // Certificate loading tests
  RUN_TEST(test_certificate_manager_load_certificates_to_client);
  RUN_TEST(test_certificate_manager_load_fails_without_ca_cert);
  RUN_TEST(test_certificate_manager_load_fails_without_provisioning);

  // Certificate clearing tests
  RUN_TEST(test_certificate_manager_clear_removes_all_data);
  RUN_TEST(test_certificate_manager_clear_clears_nvs);

  // Provisioning mode tests
  RUN_TEST(test_certificate_manager_start_provisioning_mode);
  RUN_TEST(test_certificate_manager_stop_provisioning_mode);
  RUN_TEST(test_certificate_manager_provisioning_loop);
  RUN_TEST(test_certificate_manager_provision_request_with_valid_certs);
  RUN_TEST(test_certificate_manager_provision_request_missing_fields);
  RUN_TEST(test_certificate_manager_provision_request_missing_location);
  RUN_TEST(test_certificate_manager_provision_stores_location);
  RUN_TEST(test_certificate_manager_location_persists_across_instances);

  // CN extraction tests
  RUN_TEST(test_certificate_manager_extract_cn_from_certificate);

  // Persistence tests
  RUN_TEST(test_certificate_manager_persistence_across_instances);

  return UNITY_END();
}

#ifdef UNIT_TEST
void setup() { UNITY_BEGIN(); }

void loop() {
  RUN_TEST(test_certificate_manager_begin_no_certificates);
  RUN_TEST(test_certificate_manager_begin_with_valid_certificates);
  RUN_TEST(test_certificate_manager_store_valid_certificates);
  RUN_TEST(test_certificate_manager_store_without_ca_cert);
  RUN_TEST(test_certificate_manager_reject_invalid_certificate);
  RUN_TEST(test_certificate_manager_reject_invalid_key);
  RUN_TEST(test_certificate_manager_increment_version_on_store);
  RUN_TEST(test_certificate_manager_validate_after_store);
  RUN_TEST(test_certificate_manager_validate_fails_without_certificates);
  RUN_TEST(test_certificate_manager_detect_expiration_warning);
  RUN_TEST(test_certificate_manager_validate_fails_when_current_time_unavailable);
  RUN_TEST(test_certificate_manager_load_certificates_to_client);
  RUN_TEST(test_certificate_manager_load_fails_without_ca_cert);
  RUN_TEST(test_certificate_manager_load_fails_without_provisioning);
  RUN_TEST(test_certificate_manager_clear_removes_all_data);
  RUN_TEST(test_certificate_manager_clear_clears_nvs);
  RUN_TEST(test_certificate_manager_start_provisioning_mode);
  RUN_TEST(test_certificate_manager_stop_provisioning_mode);
  RUN_TEST(test_certificate_manager_provisioning_loop);
  RUN_TEST(test_certificate_manager_provision_request_with_valid_certs);
  RUN_TEST(test_certificate_manager_provision_request_missing_fields);
  RUN_TEST(test_certificate_manager_provision_request_missing_location);
  RUN_TEST(test_certificate_manager_provision_stores_location);
  RUN_TEST(test_certificate_manager_location_persists_across_instances);
  RUN_TEST(test_certificate_manager_extract_cn_from_certificate);
  RUN_TEST(test_certificate_manager_persistence_across_instances);
  UNITY_END();
}
#endif
