#include <string.h>
#include <unity.h>

#include "../../lib/I2CAddressList/I2CAddressList.h"

// Include implementation files for linking
#include "../../lib/I2CAddressList/I2CAddressList.cpp"

void setUp(void) {}

void tearDown(void) {}

void test_append_no_addresses_writes_none() {
  char buffer[32] = "found: ";

  appendI2CAddresses(buffer, sizeof(buffer), nullptr, 0);

  TEST_ASSERT_EQUAL_STRING("found: none", buffer);
}

void test_append_addresses_joins_them_after_existing_text() {
  char buffer[32] = "found: ";
  const uint8_t addresses[] = {0x3C, 0x76};

  appendI2CAddresses(buffer, sizeof(buffer), addresses, 2);

  TEST_ASSERT_EQUAL_STRING("found: 0x3C, 0x76", buffer);
}

void test_append_too_many_addresses_stops_at_last_whole_entry() {
  // Every address ACKs when SDA is stuck low; this list overflowed the old buffer.
  uint8_t addresses[126];
  for (size_t i = 0; i < sizeof(addresses); i++) {
    addresses[i] = static_cast<uint8_t>(i + 1);
  }
  char buffer[16 + 4];
  memset(buffer, '#', sizeof(buffer));
  buffer[0] = '\0';

  appendI2CAddresses(buffer, 16, addresses, sizeof(addresses));

  // ", 0x03" would need 17 bytes; it is dropped rather than left as ", 0x0".
  TEST_ASSERT_EQUAL_STRING("0x01, 0x02", buffer);
  TEST_ASSERT_EQUAL_MEMORY("####", buffer + 16, 4);
}

void test_append_to_unterminated_buffer_leaves_it_untouched() {
  char buffer[4 + 4];
  memset(buffer, '#', sizeof(buffer));
  const uint8_t addresses[] = {0x76};

  appendI2CAddresses(buffer, 4, addresses, 1);

  TEST_ASSERT_EQUAL_MEMORY("########", buffer, sizeof(buffer));
}

int main(int argc, char **argv) {
  UNITY_BEGIN();

  RUN_TEST(test_append_no_addresses_writes_none);
  RUN_TEST(test_append_addresses_joins_them_after_existing_text);
  RUN_TEST(test_append_too_many_addresses_stops_at_last_whole_entry);
  RUN_TEST(test_append_to_unterminated_buffer_leaves_it_untouched);

  return UNITY_END();
}
