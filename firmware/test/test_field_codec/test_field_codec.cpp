#include <unity.h>

#include "../../lib/BleProvisioning/include/FieldCodec.h"

void setUp(void) {}

void tearDown(void) {}

const uint8_t *bytes(const char *s) { return reinterpret_cast<const uint8_t *>(s); }

// The adapter once cut every server name to 3 characters (it took the size of a pointer).
void test_copy_string_keeps_a_whole_server_name() {
  char dst[255];

  copyString(dst, bytes("meteo.taram.ca"), 14);

  TEST_ASSERT_EQUAL_STRING("meteo.taram.ca", dst);
}

void test_copy_string_cuts_what_does_not_fit() {
  char dst[4];

  copyString(dst, bytes("meteo"), 5);

  TEST_ASSERT_EQUAL_STRING("met", dst);
}

void test_copy_string_of_nothing_is_empty() {
  char dst[4] = "old";

  copyString(dst, bytes(""), 0);

  TEST_ASSERT_EQUAL_STRING("", dst);
}

void test_port_is_little_endian() {
  const uint8_t value[] = {0xb3, 0x22};

  TEST_ASSERT_EQUAL_UINT16(8883, decodePort(value, sizeof(value)));
}

void test_port_of_the_wrong_length_is_zero() {
  const uint8_t value[] = {0xb3, 0x22, 0x00};

  TEST_ASSERT_EQUAL_UINT16(0, decodePort(value, 1));
  TEST_ASSERT_EQUAL_UINT16(0, decodePort(value, 3));
}

void test_port_encodes_low_byte_first() {
  uint8_t out[2];

  encodePort(8883, out);

  const uint8_t expected[] = {0xb3, 0x22};
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, out, 2);
}

void test_interval_is_little_endian() {
  const uint8_t day[] = {0x80, 0x51, 0x01, 0x00};

  TEST_ASSERT_EQUAL_UINT32(86400, decodeInterval(day, sizeof(day)));
}

void test_interval_of_the_wrong_length_is_zero() {
  const uint8_t value[] = {0x10, 0x0e, 0x00, 0x00, 0x00};

  TEST_ASSERT_EQUAL_UINT32(0, decodeInterval(value, 2));
  TEST_ASSERT_EQUAL_UINT32(0, decodeInterval(value, 5));
}

void test_interval_encodes_low_byte_first() {
  uint8_t out[4];

  encodeInterval(86400, out);

  const uint8_t expected[] = {0x80, 0x51, 0x01, 0x00};
  TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, out, 4);
}

// The same bytes the app's BleTest sends for (1.0, -2.0): 0x3f800000 and 0xc0000000, low byte first.
void test_location_is_two_little_endian_floats() {
  const uint8_t value[] = {0x00, 0x00, 0x80, 0x3f, 0x00, 0x00, 0x00, 0xc0};
  float latitude = 0.0f;
  float longitude = 0.0f;

  TEST_ASSERT_TRUE(decodeLocation(value, sizeof(value), latitude, longitude));

  TEST_ASSERT_EQUAL_FLOAT(1.0f, latitude);
  TEST_ASSERT_EQUAL_FLOAT(-2.0f, longitude);
}

void test_location_of_the_wrong_length_keeps_the_old_one() {
  const uint8_t value[] = {0x00, 0x00, 0x80, 0x3f, 0x00, 0x00, 0x00, 0xc0, 0x00};
  float latitude = 45.5f;
  float longitude = -73.6f;

  TEST_ASSERT_FALSE(decodeLocation(value, 4, latitude, longitude));
  TEST_ASSERT_FALSE(decodeLocation(value, 9, latitude, longitude));

  TEST_ASSERT_EQUAL_FLOAT(45.5f, latitude);
  TEST_ASSERT_EQUAL_FLOAT(-73.6f, longitude);
}

int main(int argc, char **argv) {
  UNITY_BEGIN();
  RUN_TEST(test_copy_string_keeps_a_whole_server_name);
  RUN_TEST(test_copy_string_cuts_what_does_not_fit);
  RUN_TEST(test_copy_string_of_nothing_is_empty);
  RUN_TEST(test_port_is_little_endian);
  RUN_TEST(test_port_of_the_wrong_length_is_zero);
  RUN_TEST(test_port_encodes_low_byte_first);
  RUN_TEST(test_interval_is_little_endian);
  RUN_TEST(test_interval_of_the_wrong_length_is_zero);
  RUN_TEST(test_interval_encodes_low_byte_first);
  RUN_TEST(test_location_is_two_little_endian_floats);
  RUN_TEST(test_location_of_the_wrong_length_keeps_the_old_one);
  return UNITY_END();
}
