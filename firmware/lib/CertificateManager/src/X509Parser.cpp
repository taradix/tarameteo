#include "X509Parser.h"
#include <string.h>
#include <stdio.h>

#ifndef UNIT_TEST
// Real mbedTLS implementation for ESP32
#include <mbedtls/x509_crt.h>
#include <mbedtls/pk.h>
#include <mbedtls/error.h>
#include <mbedtls/md.h>
#include <mbedtls/oid.h>
#include <time.h>

bool X509Parser::extractCN(const char* certPem, char* cnBuffer, size_t bufferSize) {
    if (!certPem || !cnBuffer || bufferSize == 0) {
        return false;
    }

    mbedtls_x509_crt cert;
    mbedtls_x509_crt_init(&cert);

    // Parse the PEM certificate
    int ret = mbedtls_x509_crt_parse(&cert,
                                      (const unsigned char*)certPem,
                                      strlen(certPem) + 1);
    if (ret != 0) {
        mbedtls_x509_crt_free(&cert);
        return false;
    }

    // Extract CN from the subject DN
    const mbedtls_x509_name* subject = &cert.subject;
    bool found = false;

    while (subject != NULL) {
        // CN has OID 2.5.4.3
        if (MBEDTLS_OID_CMP(MBEDTLS_OID_AT_CN, &subject->oid) == 0) {
            size_t len = subject->val.len;
            if (len >= bufferSize) {
                len = bufferSize - 1;
            }
            memcpy(cnBuffer, subject->val.p, len);
            cnBuffer[len] = '\0';
            found = true;
            break;
        }
        subject = subject->next;
    }

    mbedtls_x509_crt_free(&cert);
    return found;
}

bool X509Parser::extractExpiration(const char* certPem, unsigned long* expiresAt) {
    if (!certPem || !expiresAt) {
        return false;
    }

    mbedtls_x509_crt cert;
    mbedtls_x509_crt_init(&cert);

    int ret = mbedtls_x509_crt_parse(&cert,
                                      (const unsigned char*)certPem,
                                      strlen(certPem) + 1);
    if (ret != 0) {
        mbedtls_x509_crt_free(&cert);
        return false;
    }

    // Extract notAfter (expiration) time
    const mbedtls_x509_time* notAfter = &cert.valid_to;

    // Convert to Unix epoch timestamp
    *expiresAt = timeToEpoch(notAfter->year,
                             notAfter->mon,
                             notAfter->day,
                             notAfter->hour,
                             notAfter->min,
                             notAfter->sec);

    mbedtls_x509_crt_free(&cert);
    return true;
}

bool X509Parser::extractSerial(const char* certPem, char* serialBuffer, size_t bufferSize) {
    if (!certPem || !serialBuffer || bufferSize < 3) {
        return false;
    }

    mbedtls_x509_crt cert;
    mbedtls_x509_crt_init(&cert);

    int ret = mbedtls_x509_crt_parse(&cert,
                                      (const unsigned char*)certPem,
                                      strlen(certPem) + 1);
    if (ret != 0) {
        mbedtls_x509_crt_free(&cert);
        return false;
    }

    // Convert serial number to hex string
    const mbedtls_x509_buf* serial = &cert.serial;
    size_t offset = 0;

    for (size_t i = 0; i < serial->len && offset < bufferSize - 3; i++) {
        snprintf(serialBuffer + offset, bufferSize - offset, "%02X", serial->p[i]);
        offset += 2;
    }
    serialBuffer[offset] = '\0';

    mbedtls_x509_crt_free(&cert);
    return true;
}

bool X509Parser::validateKeyPair(const char* certPem, const char* keyPem) {
    if (!certPem || !keyPem) {
        return false;
    }

    mbedtls_x509_crt cert;
    mbedtls_pk_context pk;

    mbedtls_x509_crt_init(&cert);
    mbedtls_pk_init(&pk);

    // Parse certificate
    int ret = mbedtls_x509_crt_parse(&cert,
                                      (const unsigned char*)certPem,
                                      strlen(certPem) + 1);
    if (ret != 0) {
        mbedtls_x509_crt_free(&cert);
        mbedtls_pk_free(&pk);
        return false;
    }

    // Parse private key
    ret = mbedtls_pk_parse_key(&pk,
                               (const unsigned char*)keyPem,
                               strlen(keyPem) + 1,
                               NULL, 0); // No password
    if (ret != 0) {
        mbedtls_x509_crt_free(&cert);
        mbedtls_pk_free(&pk);
        return false;
    }

    // Verify that the key types match
    mbedtls_pk_type_t cert_pk_type = mbedtls_pk_get_type(&cert.pk);
    mbedtls_pk_type_t key_pk_type = mbedtls_pk_get_type(&pk);

    if (cert_pk_type != key_pk_type) {
        mbedtls_x509_crt_free(&cert);
        mbedtls_pk_free(&pk);
        return false;
    }

    // For RSA keys, verify modulus matches
    if (cert_pk_type == MBEDTLS_PK_RSA) {
        mbedtls_rsa_context* cert_rsa = mbedtls_pk_rsa(cert.pk);
        mbedtls_rsa_context* key_rsa = mbedtls_pk_rsa(pk);

        // Compare the modulus (n) of both keys
        bool match = (mbedtls_mpi_cmp_mpi(&cert_rsa->N, &key_rsa->N) == 0);

        mbedtls_x509_crt_free(&cert);
        mbedtls_pk_free(&pk);
        return match;
    }

    // For EC keys, compare the public key points
    if (cert_pk_type == MBEDTLS_PK_ECKEY || cert_pk_type == MBEDTLS_PK_ECDSA) {
        mbedtls_ecp_keypair* cert_ec = mbedtls_pk_ec(cert.pk);
        mbedtls_ecp_keypair* key_ec = mbedtls_pk_ec(pk);

        // Compare the EC public key points
        bool match = (mbedtls_ecp_point_cmp(&cert_ec->Q, &key_ec->Q) == 0);

        mbedtls_x509_crt_free(&cert);
        mbedtls_pk_free(&pk);
        return match;
    }

    // Unknown key type
    mbedtls_x509_crt_free(&cert);
    mbedtls_pk_free(&pk);
    return false;
}

bool X509Parser::getCertificateInfo(const char* certPem, char* infoBuffer, size_t bufferSize) {
    if (!certPem || !infoBuffer || bufferSize == 0) {
        return false;
    }

    mbedtls_x509_crt cert;
    mbedtls_x509_crt_init(&cert);

    int ret = mbedtls_x509_crt_parse(&cert,
                                      (const unsigned char*)certPem,
                                      strlen(certPem) + 1);
    if (ret != 0) {
        mbedtls_x509_crt_free(&cert);
        return false;
    }

    // Use mbedtls_x509_crt_info to get formatted certificate information
    ret = mbedtls_x509_crt_info(infoBuffer, bufferSize, "  ", &cert);

    mbedtls_x509_crt_free(&cert);
    return (ret >= 0);
}

unsigned long X509Parser::timeToEpoch(int year, int month, int day, int hour, int min, int sec) {
    // Simple conversion to Unix epoch (seconds since Jan 1, 1970)
    // This is approximate and doesn't handle all edge cases perfectly

    struct tm timeinfo = {0};
    timeinfo.tm_year = year - 1900;  // Years since 1900
    timeinfo.tm_mon = month - 1;     // 0-11
    timeinfo.tm_mday = day;          // 1-31
    timeinfo.tm_hour = hour;         // 0-23
    timeinfo.tm_min = min;           // 0-59
    timeinfo.tm_sec = sec;           // 0-59

    time_t epoch = mktime(&timeinfo);
    return (unsigned long)epoch;
}

#else
// Mock implementation for unit tests
// In tests, we do simplified parsing without mbedTLS

bool X509Parser::extractCN(const char* certPem, char* cnBuffer, size_t bufferSize) {
    if (!certPem || !cnBuffer || bufferSize == 0) {
        return false;
    }

    // Simple string search fallback for testing
    const char *cnStart = strstr(certPem, "CN=");
    if (!cnStart) {
        return false;
    }
    cnStart += 3;

    size_t i = 0;
    while (i < bufferSize - 1 && cnStart[i] != '\0' &&
           cnStart[i] != ',' && cnStart[i] != '\n' && cnStart[i] != '\r') {
        cnBuffer[i] = cnStart[i];
        i++;
    }
    cnBuffer[i] = '\0';

    return (i > 0);
}

bool X509Parser::extractExpiration(const char* certPem, unsigned long* expiresAt) {
    if (!certPem || !expiresAt) {
        return false;
    }

    // For testing: set to a future date (May 2033)
    *expiresAt = 2000000000UL;
    return true;
}

bool X509Parser::extractSerial(const char* certPem, char* serialBuffer, size_t bufferSize) {
    if (!certPem || !serialBuffer || bufferSize < 3) {
        return false;
    }

    // Mock serial for testing
    snprintf(serialBuffer, bufferSize, "0123456789ABCDEF");
    return true;
}

bool X509Parser::validateKeyPair(const char* certPem, const char* keyPem) {
    if (!certPem || !keyPem) {
        return false;
    }

    // Basic format validation for testing
    bool hasCert = (strstr(certPem, "-----BEGIN CERTIFICATE-----") != nullptr);
    bool hasKey = (strstr(keyPem, "-----BEGIN") != nullptr) &&
                  (strstr(keyPem, "PRIVATE KEY-----") != nullptr);

    return hasCert && hasKey;
}

bool X509Parser::getCertificateInfo(const char* certPem, char* infoBuffer, size_t bufferSize) {
    if (!certPem || !infoBuffer || bufferSize == 0) {
        return false;
    }

    snprintf(infoBuffer, bufferSize, "Mock certificate info");
    return true;
}

unsigned long X509Parser::timeToEpoch(int year, int month, int day, int hour, int min, int sec) {
    // Simplified calculation for testing
    return 946684800UL; // Jan 1, 2000
}

#endif // UNIT_TEST
