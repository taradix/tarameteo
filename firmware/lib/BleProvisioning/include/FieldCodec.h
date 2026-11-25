#ifndef FIELD_CODEC_H
#define FIELD_CODEC_H

#include <cstddef>
#include <cstdint>
#include <cstring>

#include "IBleProvisioner.h"

// The byte formats of the provisioning characteristics (IBleProvisioner.h), apart
// from NimBLE so the host tests cover them.

// Copies a written string field into dst, NUL-terminated, cut to fit. Takes the
// buffer itself, so its size can't be taken from the wrong one.
template <size_t N> void copyString(char (&dst)[N], const uint8_t *data, size_t len) {
  size_t n = (len < N - 1) ? len : N - 1;
  memcpy(dst, data, n);
  dst[n] = '\0';
}

// Port: LE uint16. A value of the wrong length decodes as 0, which applyProvisioning rejects.
inline uint16_t decodePort(const uint8_t *data, size_t len) {
  return (len == 2) ? (uint16_t)(data[0] | (data[1] << 8)) : 0;
}

inline void encodePort(uint16_t port, uint8_t (&out)[2]) {
  out[0] = (uint8_t)port;
  out[1] = (uint8_t)(port >> 8);
}

// Interval: LE uint32 seconds, likewise.
inline uint32_t decodeInterval(const uint8_t *data, size_t len) {
  if (len != 4) {
    return 0;
  }
  return (uint32_t)data[0] | ((uint32_t)data[1] << 8) | ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);
}

inline void encodeInterval(uint32_t interval, uint8_t (&out)[4]) {
  out[0] = (uint8_t)interval;
  out[1] = (uint8_t)(interval >> 8);
  out[2] = (uint8_t)(interval >> 16);
  out[3] = (uint8_t)(interval >> 24);
}

// Location: LE float32 latitude, then LE float32 longitude. A value of the wrong
// length leaves both as they were, so the board keeps its location.
inline bool decodeLocation(const uint8_t *data, size_t len, float &latitude, float &longitude) {
  if (len != 8) {
    return false;
  }
  uint32_t bits[2];
  for (int i = 0; i < 2; i++) {
    const uint8_t *b = data + 4 * i;
    bits[i] = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
  }
  memcpy(&latitude, &bits[0], 4);
  memcpy(&longitude, &bits[1], 4);
  return true;
}

// Commit: one BleCommit byte. Anything else, a wrong length too, is Unknown, which the
// board answers with "error:commit" rather than leaving the client waiting.
inline BleRequest decodeCommit(const uint8_t *data, size_t len) {
  if (len != 1) {
    return BleRequest::Unknown;
  }
  switch (data[0]) {
  case BleCommit::PROVISION:
    return BleRequest::Provision;
  case BleCommit::RESET:
    return BleRequest::Reset;
  default:
    return BleRequest::Unknown;
  }
}

#endif // FIELD_CODEC_H
