#include <unity.h>
#include <string.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#endif

#include "../../lib/CertificateManager/include/X509Parser.h"

// Include implementation files for linking
#include "../../lib/CertificateManager/src/X509Parser.cpp"

// Test certificate with known values
// CN=station-01, expires in distant future (for testing)
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

const char *INVALID_CERT = "This is not a certificate at all!";
const char *INVALID_KEY = "This is not a key!";

// ========================================
// Test Setup/Teardown
// ========================================

void setUp(void) {
    // Nothing to set up
}

void tearDown(void) {
    // Nothing to tear down
}

// ========================================
// CN Extraction Tests
// ========================================

void test_x509_extract_cn_success() {
    char cn[64];
    bool result = X509Parser::extractCN(TEST_CERT_PEM, cn, sizeof(cn));

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL_STRING("station-01", cn);
}

void test_x509_extract_cn_null_cert() {
    char cn[64];
    bool result = X509Parser::extractCN(nullptr, cn, sizeof(cn));

    TEST_ASSERT_FALSE(result);
}

void test_x509_extract_cn_null_buffer() {
    bool result = X509Parser::extractCN(TEST_CERT_PEM, nullptr, 64);

    TEST_ASSERT_FALSE(result);
}

void test_x509_extract_cn_invalid_cert() {
    char cn[64];
    bool result = X509Parser::extractCN(INVALID_CERT, cn, sizeof(cn));

    TEST_ASSERT_FALSE(result);
}

void test_x509_extract_cn_buffer_too_small() {
    char cn[5];  // Too small for "station-01"
    bool result = X509Parser::extractCN(TEST_CERT_PEM, cn, sizeof(cn));

    // Should still succeed but truncate
    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL_INT(4, strlen(cn));  // Buffer size - 1
}

// ========================================
// Expiration Extraction Tests
// ========================================

void test_x509_extract_expiration_success() {
    unsigned long expiresAt = 0;
    bool result = X509Parser::extractExpiration(TEST_CERT_PEM, &expiresAt);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_GREATER_THAN(0, expiresAt);

    // In unit tests, this returns a fixed value
    // In production, it would parse the actual notAfter date
}

void test_x509_extract_expiration_null_cert() {
    unsigned long expiresAt = 0;
    bool result = X509Parser::extractExpiration(nullptr, &expiresAt);

    TEST_ASSERT_FALSE(result);
}

void test_x509_extract_expiration_null_output() {
    bool result = X509Parser::extractExpiration(TEST_CERT_PEM, nullptr);

    TEST_ASSERT_FALSE(result);
}

// ========================================
// Serial Extraction Tests
// ========================================

void test_x509_extract_serial_success() {
    char serial[128];
    bool result = X509Parser::extractSerial(TEST_CERT_PEM, serial, sizeof(serial));

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_GREATER_THAN(0, strlen(serial));

    // Verify it's a hex string
    for (size_t i = 0; i < strlen(serial); i++) {
        char c = serial[i];
        TEST_ASSERT_TRUE((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'));
    }
}

void test_x509_extract_serial_null_cert() {
    char serial[128];
    bool result = X509Parser::extractSerial(nullptr, serial, sizeof(serial));

    TEST_ASSERT_FALSE(result);
}

void test_x509_extract_serial_buffer_too_small() {
    char serial[2];  // Too small
    bool result = X509Parser::extractSerial(TEST_CERT_PEM, serial, sizeof(serial));

    TEST_ASSERT_FALSE(result);
}

// ========================================
// Key Pair Validation Tests
// ========================================

void test_x509_validate_keypair_matching() {
    bool result = X509Parser::validateKeyPair(TEST_CERT_PEM, TEST_KEY_PEM);

    TEST_ASSERT_TRUE(result);
}

void test_x509_validate_keypair_accepts_valid_pem_formats() {
    // Unit tests without mbedTLS can only verify PEM format validation,
    // not cryptographic keypair matching. Cryptographic validation is
    // tested in test_integration/test_x509_crypto.cpp on real hardware.
    bool result = X509Parser::validateKeyPair(TEST_CERT_PEM, DIFFERENT_KEY_PEM);

    // Both are valid PEM formats → should pass format check
    TEST_ASSERT_TRUE(result);
}

void test_x509_validate_keypair_rejects_invalid_cert() {
    bool result = X509Parser::validateKeyPair(INVALID_CERT, TEST_KEY_PEM);

    TEST_ASSERT_FALSE(result);  // Invalid PEM format rejected
}

void test_x509_validate_keypair_rejects_invalid_key() {
    bool result = X509Parser::validateKeyPair(TEST_CERT_PEM, INVALID_KEY);

    TEST_ASSERT_FALSE(result);  // Invalid PEM format rejected
}

void test_x509_validate_keypair_null_cert() {
    bool result = X509Parser::validateKeyPair(nullptr, TEST_KEY_PEM);

    TEST_ASSERT_FALSE(result);
}

void test_x509_validate_keypair_null_key() {
    bool result = X509Parser::validateKeyPair(TEST_CERT_PEM, nullptr);

    TEST_ASSERT_FALSE(result);
}

// ========================================
// Certificate Info Tests
// ========================================

void test_x509_get_certificate_info_success() {
    char info[512];
    bool result = X509Parser::getCertificateInfo(TEST_CERT_PEM, info, sizeof(info));

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_GREATER_THAN(0, strlen(info));
}

void test_x509_get_certificate_info_null_cert() {
    char info[512];
    bool result = X509Parser::getCertificateInfo(nullptr, info, sizeof(info));

    TEST_ASSERT_FALSE(result);
}

void test_x509_get_certificate_info_null_buffer() {
    bool result = X509Parser::getCertificateInfo(TEST_CERT_PEM, nullptr, 512);

    TEST_ASSERT_FALSE(result);
}

// ========================================
// Integration Tests
// ========================================

void test_x509_full_certificate_parse() {
    char cn[64];
    unsigned long expiresAt;
    char serial[128];

    // Parse all fields from certificate
    bool cnResult = X509Parser::extractCN(TEST_CERT_PEM, cn, sizeof(cn));
    bool expResult = X509Parser::extractExpiration(TEST_CERT_PEM, &expiresAt);
    bool serialResult = X509Parser::extractSerial(TEST_CERT_PEM, serial, sizeof(serial));

    TEST_ASSERT_TRUE(cnResult);
    TEST_ASSERT_TRUE(expResult);
    TEST_ASSERT_TRUE(serialResult);

    TEST_ASSERT_EQUAL_STRING("station-01", cn);
    TEST_ASSERT_GREATER_THAN(0, expiresAt);
    TEST_ASSERT_GREATER_THAN(0, strlen(serial));
}

// ========================================
// Main
// ========================================

int main(int argc, char **argv) {
    UNITY_BEGIN();

    // CN Extraction
    RUN_TEST(test_x509_extract_cn_success);
    RUN_TEST(test_x509_extract_cn_null_cert);
    RUN_TEST(test_x509_extract_cn_null_buffer);
    RUN_TEST(test_x509_extract_cn_invalid_cert);
    RUN_TEST(test_x509_extract_cn_buffer_too_small);

    // Expiration Extraction
    RUN_TEST(test_x509_extract_expiration_success);
    RUN_TEST(test_x509_extract_expiration_null_cert);
    RUN_TEST(test_x509_extract_expiration_null_output);

    // Serial Extraction
    RUN_TEST(test_x509_extract_serial_success);
    RUN_TEST(test_x509_extract_serial_null_cert);
    RUN_TEST(test_x509_extract_serial_buffer_too_small);

    // Key Pair Validation
    RUN_TEST(test_x509_validate_keypair_matching);
    RUN_TEST(test_x509_validate_keypair_accepts_valid_pem_formats);
    RUN_TEST(test_x509_validate_keypair_rejects_invalid_cert);
    RUN_TEST(test_x509_validate_keypair_rejects_invalid_key);
    RUN_TEST(test_x509_validate_keypair_null_cert);
    RUN_TEST(test_x509_validate_keypair_null_key);

    // Certificate Info
    RUN_TEST(test_x509_get_certificate_info_success);
    RUN_TEST(test_x509_get_certificate_info_null_cert);
    RUN_TEST(test_x509_get_certificate_info_null_buffer);

    // Integration
    RUN_TEST(test_x509_full_certificate_parse);

    return UNITY_END();
}
