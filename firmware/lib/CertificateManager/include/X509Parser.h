#ifndef X509_PARSER_H
#define X509_PARSER_H

#include <stddef.h>
#include <stdint.h>

/**
 * @brief Lightweight X.509 certificate parser for ESP32
 *
 * This class wraps mbedTLS X.509 functions to provide certificate parsing
 * capabilities while keeping the interface testable.
 */
class X509Parser {
public:
    static const int MAX_CN_LENGTH = 64;

    /**
     * @brief Extract the Common Name (CN) from a PEM certificate
     *
     * @param certPem PEM-encoded certificate string
     * @param cnBuffer Buffer to store the extracted CN
     * @param bufferSize Size of the CN buffer
     * @return true if CN was successfully extracted, false otherwise
     */
    static bool extractCN(const char* certPem, char* cnBuffer, size_t bufferSize);
};

#endif // X509_PARSER_H
