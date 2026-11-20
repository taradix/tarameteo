#ifndef I2C_ADDRESS_LIST_H
#define I2C_ADDRESS_LIST_H

#include <stddef.h>
#include <stdint.h>

// Appends the addresses as "0x76, 0x77", or "none" when count is 0, to the
// NUL-terminated string in buffer. Stops at the last entry that fits whole, so
// a full buffer never ends in a partial address.
void appendI2CAddresses(char *buffer, size_t size, const uint8_t *addresses, size_t count);

#endif // I2C_ADDRESS_LIST_H
