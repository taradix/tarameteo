// app.json holds the config; this only adds what can't be committed.
module.exports = ({ config }) => ({
  ...config,
  android: {
    ...config.android,
    // Set in EAS (eas env:create); restricted to ca.taram.meteo and the EAS keystore's SHA-1.
    config: { googleMaps: { apiKey: process.env.GOOGLE_MAPS_API_KEY } },
  },
  plugins: [
    ...config.plugins,
    [
      "expo-location",
      { locationWhenInUsePermission: "TaraMeteo uses your location to show nearby sensors." },
    ],
    // R8 strips classes loaded by reflection (WorkManager's Room database, via react-native-maps)
    // and the app crashes at launch. ponytail: no shrinking, bigger APK; add keep rules if size matters.
    ["expo-build-properties", { android: { enableMinifyInReleaseBuilds: false } }],
  ],
});
