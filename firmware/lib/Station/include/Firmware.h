#ifndef FIRMWARE_H
#define FIRMWARE_H

// What this image is, set by the build: the PlatformIO env it was built for
// (platformio.ini), which names the images the backend offers it, and the release
// version (the firmware-release workflow). Local builds are FIRMWARE_DEV_VERSION.
#ifndef FIRMWARE_BOARD
#define FIRMWARE_BOARD "native"
#endif
// A local build, which never updates; the Makefile's FIRMWARE_VERSION default too.
#define FIRMWARE_DEV_VERSION "dev"
#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION FIRMWARE_DEV_VERSION
#endif

#endif // FIRMWARE_H
