// One module: the app lives at the project root.
plugins {
    id("com.android.application") version "9.5.1"
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21"
    id("org.jetbrains.kotlin.plugin.serialization") version "2.4.21"
}

val openapi = file("../backend/openapi.json")

android {
    namespace = "ca.taram.meteo"
    compileSdk = 37

    defaultConfig {
        applicationId = "ca.taram.meteo"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.0.0"
        // Point at a dev backend with -PapiBase=... or apiBase=... in ~/.gradle/gradle.properties.
        val apiBase = providers.gradleProperty("apiBase").getOrElse("https://meteo.taram.ca")
        buildConfigField("String", "API_BASE", "\"$apiBase\"")
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
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.13.0")

    testImplementation("junit:junit:4.13.2")
}
