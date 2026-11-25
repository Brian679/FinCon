rootProject.name = "ChipingeRDC"

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

// shared      : offline database (SQLDelight), API client (Ktor), sync engine, common UI kit
// councilApp  : Council staff app (Android + iOS) - role-based, offline-first
// clientApp   : Community / ratepayer app (Android + iOS) - pay rates, licences, report problems
include(":shared")
include(":councilApp")
include(":clientApp")
