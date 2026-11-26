#include <string>
#include <unity.h>

#include "../../lib/OtaUpdater/OtaUpdater.h"

// Include implementation files for linking
#include "../../lib/OtaUpdater/OtaUpdater.cpp"

// Bytes whose hex digits differ, so a swapped digit order shows.
static const char *SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

Preferences prefs;

void setUp(void) { prefs.clear(); }

void tearDown(void) { prefs.end(); }

// What the backend publishes, with field overrides.
static std::string manifest(const std::string &version = "\"1.2.0\"", const std::string &sha256 = SHA256,
                            const std::string &size = "1048576") {
  return "{\"version\":" + version + ",\"sha256\":\"" + sha256 + "\",\"size\":" + size +
         ",\"url\":\"https://meteo.taram.ca/api/firmware/esp32/1.2.0.bin\"}";
}

void test_parse_manifest() {
  std::string json = manifest();
  FirmwareManifest m;

  TEST_ASSERT_TRUE(parseManifest(json.c_str(), json.size(), m));
  TEST_ASSERT_EQUAL_STRING("1.2.0", m.version);
  TEST_ASSERT_EQUAL_STRING("https://meteo.taram.ca/api/firmware/esp32/1.2.0.bin", m.url);
  TEST_ASSERT_EQUAL_UINT32(1048576, m.size);
  const uint8_t sha256[] = {0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef};
  for (int i = 0; i < 32; i += 8) {
    TEST_ASSERT_EQUAL_UINT8_ARRAY(sha256, m.sha256 + i, 8);
  }
}

void test_parse_manifest_rejects_malformed() {
  const std::string bad[] = {
      "not json",
      manifest("\"\""),                                                                // empty version
      manifest("\"" + std::string(65, 'v') + "\""),                                    // version too long
      manifest("\"1.2.0\"", std::string(63, 'a')),                                     // short sha256
      manifest("\"1.2.0\"", std::string(64, 'A')),                                     // uppercase hex
      manifest("\"1.2.0\"", std::string(64, 'g')),                                     // not hex
      manifest("\"1.2.0\"", SHA256, "0"),                                              // no size
      "{\"version\":\"1.2.0\",\"sha256\":\"" + std::string(SHA256) + "\",\"size\":1}", // no url
  };
  for (const std::string &json : bad) {
    FirmwareManifest m;
    TEST_ASSERT_FALSE_MESSAGE(parseManifest(json.c_str(), json.size(), m), json.c_str());
  }
}

void test_updates_are_enabled_for_releases_with_auto_update_on() {
  TEST_ASSERT_TRUE(updatesEnabled("1.2.0", true));
  TEST_ASSERT_FALSE(updatesEnabled("1.2.0", false)); // owner turned it off
  TEST_ASSERT_FALSE(updatesEnabled("dev", true));    // local build
}

void test_should_update_to_another_version() {
  TEST_ASSERT_TRUE(shouldUpdate("1.2.0", "1.3.0", ""));
  // Older too: publishing it rolls the fleet back.
  TEST_ASSERT_TRUE(shouldUpdate("1.2.0", "1.1.0", ""));
}

void test_should_not_update() {
  TEST_ASSERT_FALSE(shouldUpdate("1.2.0", "1.2.0", ""));      // running it
  TEST_ASSERT_FALSE(shouldUpdate("1.2.0", "1.3.0", "1.3.0")); // failed here
  TEST_ASSERT_FALSE(shouldUpdate("1.2.0", "", ""));
}

void test_begin_marks_a_rolled_back_version_bad() {
  OtaUpdater before(prefs);
  TEST_ASSERT_TRUE(before.begin("1.2.0"));
  TEST_ASSERT_TRUE(before.recordTry("1.3.0"));

  // The bootloader went back to 1.2.0.
  OtaUpdater after(prefs);
  TEST_ASSERT_TRUE(after.begin("1.2.0"));

  TEST_ASSERT_EQUAL_STRING("1.3.0", after.getBad());
  TEST_ASSERT_FALSE(prefs.isKey("tried"));
  // Still bad on later boots.
  OtaUpdater later(prefs);
  TEST_ASSERT_TRUE(later.begin("1.2.0"));
  TEST_ASSERT_EQUAL_STRING("1.3.0", later.getBad());
}

void test_begin_keeps_the_try_while_it_runs() {
  OtaUpdater before(prefs);
  TEST_ASSERT_TRUE(before.begin("1.2.0"));
  TEST_ASSERT_TRUE(before.recordTry("1.3.0"));

  // Booted into 1.3.0, pending until its first publish.
  OtaUpdater after(prefs);
  TEST_ASSERT_TRUE(after.begin("1.3.0"));

  TEST_ASSERT_EQUAL_STRING("", after.getBad());
  TEST_ASSERT_TRUE(prefs.isKey("tried"));
}

void test_begin_keeps_the_try_until_the_bad_version_is_stored() {
  OtaUpdater before(prefs);
  TEST_ASSERT_TRUE(before.begin("1.2.0"));
  TEST_ASSERT_TRUE(before.recordTry("1.3.0"));
  prefs.failWritesTo("bad");

  OtaUpdater after(prefs);
  TEST_ASSERT_TRUE(after.begin("1.2.0"));

  // Bad for this boot, and the try is left for the next boot to store it.
  TEST_ASSERT_EQUAL_STRING("1.3.0", after.getBad());
  TEST_ASSERT_TRUE(prefs.isKey("tried"));
  OtaUpdater later(prefs);
  TEST_ASSERT_TRUE(later.begin("1.2.0"));
  TEST_ASSERT_EQUAL_STRING("1.3.0", later.getBad());
}

void test_begin_on_a_new_board_has_nothing_bad() {
  OtaUpdater ota(prefs);

  TEST_ASSERT_TRUE(ota.begin("1.2.0"));
  TEST_ASSERT_EQUAL_STRING("", ota.getBad());
}

void test_record_try_failure_is_reported() {
  OtaUpdater ota(prefs);
  TEST_ASSERT_TRUE(ota.begin("1.2.0"));
  prefs.failWritesTo("tried");

  TEST_ASSERT_FALSE(ota.recordTry("1.3.0"));
  TEST_ASSERT_TRUE(strstr(ota.getLastError(), "installed version") != NULL);
}

int main(int argc, char **argv) {
  UNITY_BEGIN();
  RUN_TEST(test_parse_manifest);
  RUN_TEST(test_parse_manifest_rejects_malformed);
  RUN_TEST(test_updates_are_enabled_for_releases_with_auto_update_on);
  RUN_TEST(test_should_update_to_another_version);
  RUN_TEST(test_should_not_update);
  RUN_TEST(test_begin_marks_a_rolled_back_version_bad);
  RUN_TEST(test_begin_keeps_the_try_while_it_runs);
  RUN_TEST(test_begin_keeps_the_try_until_the_bad_version_is_stored);
  RUN_TEST(test_begin_on_a_new_board_has_nothing_bad);
  RUN_TEST(test_record_try_failure_is_reported);
  return UNITY_END();
}
