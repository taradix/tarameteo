// One module: the app lives at the project root. The Kotlin plugins' version is in settings.gradle.kts.
plugins {
    id("com.android.application") version "9.5.2"
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("com.google.gms.google-services") version "4.6.0" apply false
}

val openapi = file("../backend/openapi.json")
val bleContract = file("../firmware/lib/BleProvisioning/include/IBleProvisioner.h")
// Where the firmware bounds the settings the app sends, such as the interval.
val settingsContract = file("../firmware/lib/CertificateManager/include/CertificateManager.h")
// Push alerts need a Firebase project: drop its google-services.json next to this file. The file ships
// inside every APK, so it is not a secret; without it the app still builds, only alerts don't work.
val firebase = file("google-services.json").exists()
// Release builds are signed only when releaseKeystore is set, with releaseKeystorePassword, releaseKeyAlias and releaseKeyPassword.
val keystore = providers.gradleProperty("releaseKeystore").orNull

android {
    namespace = "ca.taram.meteo"
    // Compose 1.13 needs the 37.1 APIs; compileSdk only changes which APIs the build sees.
    compileSdk {
        version = release(37) {
            minorApiLevel = 1
        }
    }

    defaultConfig {
        applicationId = "ca.taram.meteo"
        minSdk = 26
        targetSdk = 37
        // CI passes the run number and the tag.
        versionCode = providers.gradleProperty("versionCode").getOrElse("1").toInt()
        versionName = providers.gradleProperty("versionName").getOrElse("0.0.0")
        // Point at a dev backend with -PapiBase=... or apiBase=... in ~/.gradle/gradle.properties.
        val apiBase = providers.gradleProperty("apiBase").getOrElse("https://meteo.taram.ca")
        buildConfigField("String", "API_BASE", "\"$apiBase\"")
        // mapsApiKey=... in ~/.gradle/gradle.properties; without it the map stays blank but the list works.
        manifestPlaceholders["mapsApiKey"] = providers.gradleProperty("mapsApiKey").getOrElse("none")
    }

    if (keystore != null) {
        signingConfigs.create("release") {
            storeFile = file(keystore)
            storePassword = providers.gradleProperty("releaseKeystorePassword").get()
            keyAlias = providers.gradleProperty("releaseKeyAlias").get()
            keyPassword = providers.gradleProperty("releaseKeyPassword").get()
        }
    }

    buildTypes.getByName("release") {
        // Compose is much slower without R8.
        isMinifyEnabled = true
        isShrinkResources = true
        proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        if (keystore != null) signingConfig = signingConfigs.getByName("release")
    }

    // maps-compose inlines Java 17 bytecode.
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    testOptions.unitTests.all {
        it.inputs.file(openapi)
        it.systemProperty("openapi", openapi.path)
        it.inputs.file(bleContract)
        it.systemProperty("bleContract", bleContract.path)
        it.inputs.file(settingsContract)
        it.systemProperty("settingsContract", settingsContract.path)
    }
}

dependencies {
    val coroutines = "1.11.0"
    val lifecycle = "2.11.1"
    implementation("com.google.firebase:firebase-messaging:26.0.2")
    implementation(platform("androidx.compose:compose-bom:2026.11.01"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:$lifecycle")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:$lifecycle")
    implementation("androidx.navigation:navigation-compose:2.10.2")
    implementation("com.google.maps.android:maps-compose:9.0.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:$coroutines")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.13.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:$coroutines")
}

// Reads google-services.json into the resources the Firebase SDK looks for at startup.
if (firebase) apply(plugin = "com.google.gms.google-services") else logger.warn("No google-services.json: this build has no push alerts.")
