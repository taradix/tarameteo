// One module: the app lives at the project root.
plugins {
    id("com.android.application") version "9.5.1"
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21"
    id("org.jetbrains.kotlin.plugin.serialization") version "2.4.21"
}

val openapi = file("../backend/openapi.json")
// Release builds are signed only when releaseKeystore is set, with releaseKeystorePassword, releaseKeyAlias and releaseKeyPassword.
val keystore = providers.gradleProperty("releaseKeystore").orNull

android {
    namespace = "ca.taram.meteo"
    compileSdk = 37

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
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.navigation:navigation-compose:2.10.2")
    implementation("com.google.maps.android:maps-compose:9.0.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.13.0")

    testImplementation("junit:junit:4.13.2")
}
