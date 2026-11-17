#include <unity.h>
#include <string.h>

#ifdef UNIT_TEST
#include "Arduino.h"
#endif

#include "../../lib/CertificateManager/include/X509Parser.h"

// Include implementation files for linking
#include "../../lib/CertificateManager/src/X509Parser.cpp"

// Test certificate with known values
// CN=station-01
const char *TEST_CERT_PEM =
    "-----BEGIN CERTIFICATE-----\n"
    "MIIDXTCCAkWgAwIBAgIJAKL0UG+mRCQzMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV\n"
    "BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX\n"
    "aWRnaXRzIFB0eSBMdGQwHhcNMjQwMTAxMDAwMDAwWhcNMzQwMTAxMDAwMDAwWjBF\n"
    "MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50\n"
    "ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB\n"
    "CgKCAQEAwU4qD3z9/CN=station-01\n"
    "-----END CERTIFICATE-----\n";

const char *INVALID_CERT = "This is not a certificate at all!";

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

    return UNITY_END();
}
