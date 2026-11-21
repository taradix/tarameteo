#include <unity.h>

#include "../../lib/BleProvisioning/include/NetworkList.h"

// Include implementation files for linking
#include "../../lib/BleProvisioning/src/NetworkList.cpp"

void setUp(void) {}

void tearDown(void) {}

void test_encode_no_networks_writes_nothing() {
  uint8_t out[8];

  TEST_ASSERT_EQUAL(0, encodeNetworks(nullptr, 0, out, sizeof(out)));
}

void test_encode_puts_rssi_and_length_before_each_ssid() {
  ScannedNetwork networks[] = {{"ab", -40}};
  uint8_t out[8];

  size_t written = encodeNetworks(networks, 1, out, sizeof(out));

  const uint8_t expected[] = {static_cast<uint8_t>(-40), 2, 'a', 'b'};
  TEST_ASSERT_EQUAL(sizeof(expected), written);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, out, written);
}

void test_encode_lists_strongest_first() {
  ScannedNetwork networks[] = {{"far", -85}, {"near", -40}, {"mid", -60}};
  uint8_t out[32];

  size_t written = encodeNetworks(networks, 3, out, sizeof(out));

  const uint8_t expected[] = {
      static_cast<uint8_t>(-40), 4, 'n', 'e', 'a', 'r', //
      static_cast<uint8_t>(-60), 3, 'm', 'i', 'd',      //
      static_cast<uint8_t>(-85), 3, 'f', 'a', 'r',      //
  };
  TEST_ASSERT_EQUAL(sizeof(expected), written);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, out, written);
}

void test_encode_keeps_the_strongest_access_point_of_an_ssid() {
  ScannedNetwork networks[] = {{"home", -70}, {"home", -50}};
  uint8_t out[32];

  size_t written = encodeNetworks(networks, 2, out, sizeof(out));

  const uint8_t expected[] = {static_cast<uint8_t>(-50), 4, 'h', 'o', 'm', 'e'};
  TEST_ASSERT_EQUAL(sizeof(expected), written);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, out, written);
}

void test_encode_skips_hidden_networks() {
  ScannedNetwork networks[] = {{"", -30}, {"a", -60}};
  uint8_t out[8];

  size_t written = encodeNetworks(networks, 2, out, sizeof(out));

  const uint8_t expected[] = {static_cast<uint8_t>(-60), 1, 'a'};
  TEST_ASSERT_EQUAL(sizeof(expected), written);
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, out, written);
}

void test_encode_stops_at_the_last_whole_entry_that_fits() {
  ScannedNetwork networks[] = {{"abc", -40}, {"def", -50}};
  // The second entry needs 5 more bytes than the first's 5: one short.
  uint8_t out[9];

  size_t written = encodeNetworks(networks, 2, out, sizeof(out));

  TEST_ASSERT_EQUAL(5, written);
}

int main(int argc, char **argv) {
  UNITY_BEGIN();
  RUN_TEST(test_encode_no_networks_writes_nothing);
  RUN_TEST(test_encode_puts_rssi_and_length_before_each_ssid);
  RUN_TEST(test_encode_lists_strongest_first);
  RUN_TEST(test_encode_keeps_the_strongest_access_point_of_an_ssid);
  RUN_TEST(test_encode_skips_hidden_networks);
  RUN_TEST(test_encode_stops_at_the_last_whole_entry_that_fits);
  return UNITY_END();
}
