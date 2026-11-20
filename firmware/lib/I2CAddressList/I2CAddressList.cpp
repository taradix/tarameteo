#include "I2CAddressList.h"
#include <stdio.h>
#include <string.h>

void appendI2CAddresses(char *buffer, size_t size, const uint8_t *addresses, size_t count) {
  size_t len = strnlen(buffer, size);
  if (len >= size) {
    return; // Not NUL-terminated within size; nothing can be appended safely.
  }

  if (count == 0) {
    static const char NONE[] = "none";
    if (sizeof(NONE) <= size - len) {
      memcpy(buffer + len, NONE, sizeof(NONE));
    }
    return;
  }

  // NOTE: a truncated list carries no marker; at most 126 addresses exist, so
  // size the buffer for them if the full list matters.
  for (size_t i = 0; i < count; i++) {
    int n = snprintf(buffer + len, size - len, i > 0 ? ", 0x%02X" : "0x%02X", addresses[i]);
    if (n < 0 || static_cast<size_t>(n) >= size - len) {
      buffer[len] = '\0'; // Drop the partial entry snprintf wrote.
      return;
    }
    len += static_cast<size_t>(n);
  }
}
