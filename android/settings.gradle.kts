pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    // The Kotlin plugins ship with the compiler, so they share its version. Here because a build script's
    // plugins block can't read a variable.
    val kotlin = "2.4.21"
    plugins {
        id("org.jetbrains.kotlin.plugin.compose") version kotlin
        id("org.jetbrains.kotlin.plugin.serialization") version kotlin
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "tarameteo"
