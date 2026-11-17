#include "X509Parser.h"
#include <string.h>
#include <stdio.h>

#ifndef UNIT_TEST
// Real mbedTLS implementation for ESP32
#include <mbedtls/x509_crt.h>
#include <mbedtls/oid.h>

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

#endif // UNIT_TEST
