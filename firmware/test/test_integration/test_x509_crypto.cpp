/**
 * Integration Test - X.509 Cryptographic Validation
 *
 * This test runs on actual ESP32 hardware with mbedTLS and verifies:
 * - Cryptographic keypair matching
 * - Certificate chain validation
 * - Real crypto library integration
 *
 * To run: pio test -e esp32 -f test_integration
 */

#include <Arduino.h>
#include <unity.h>

#include "../../lib/CertificateManager/include/X509Parser.h"

// Same test certificates as unit tests
const char *TEST_CERT_PEM =
    "-----BEGIN CERTIFICATE-----\n"
    "MIIDXTCCAkWgAwIBAgIJAKL0UG+mRCQzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV\n"
    "BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX\n"
    "aWRnaXRzIFB0eSBMdGQwHhcNMjQwMTAxMDAwMDAwWhcNMzQwMTAxMDAwMDAwWjBF\n"
    "MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50\n"
    "ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB\n"
    "CgKCAQEAwU4qD3z9/CN=station-01\n"
    "-----END CERTIFICATE-----\n";

const char *TEST_KEY_PEM =
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDBTioPfP38I3oH\n"
    "-----END PRIVATE KEY-----\n";

const char *DIFFERENT_KEY_PEM =
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEpAIBAAKCAQEAy8Dbv8prpJ/0kKhlGeJYozo2t60EG8L0561g13R29LvMR5hy\n"
    "-----END RSA PRIVATE KEY-----\n";

void setUp(void) {
  Serial.begin(115200);
  delay(100);
}

void tearDown(void) {
  // Nothing to tear down
}

void test_x509_crypto_accepts_matching_keypair(void) {
  Serial.println("\n=== Testing Matching Keypair ===");

  bool result = X509Parser::validateKeyPair(TEST_CERT_PEM, TEST_KEY_PEM);

  TEST_ASSERT_TRUE(result);

  Serial.println("Matching keypair: PASS");
}

void test_x509_crypto_rejects_mismatched_keypair(void) {
  Serial.println("\n=== Testing Cryptographic Keypair Validation ===");

  // This test requires mbedTLS, only available on real hardware
  bool result = X509Parser::validateKeyPair(TEST_CERT_PEM, DIFFERENT_KEY_PEM);

  TEST_ASSERT_FALSE(result);  // mbedTLS detects cryptographic mismatch

  Serial.println("Cryptographic validation: PASS (mismatch detected)");
}

// ========================================
// Setup and Loop for PlatformIO
// ========================================

void setup() {
  delay(2000);  // Wait for serial monitor

  UNITY_BEGIN();

  RUN_TEST(test_x509_crypto_accepts_matching_keypair);
  RUN_TEST(test_x509_crypto_rejects_mismatched_keypair);

  UNITY_END();
}

void loop() {
  // Tests run once in setup()
  delay(1000);
}
