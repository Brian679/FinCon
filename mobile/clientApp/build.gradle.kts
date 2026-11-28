import org.jetbrains.compose.desktop.application.dsl.TargetFormat
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
    alias(libs.plugins.kotlinSerialization)
}

kotlin {
    androidTarget {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }
    jvm("desktop") {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }
    listOf(iosX64(), iosArm64(), iosSimulatorArm64()).forEach {
        it.binaries.framework {
            baseName = "ClientApp"
            isStatic = true
            linkerOpts.add("-lsqlite3")
        }
    }
    sourceSets {
        all {
            languageSettings.optIn("androidx.compose.material3.ExperimentalMaterial3Api")
            languageSettings.optIn("kotlin.uuid.ExperimentalUuidApi")
        }
        commonMain.dependencies {
            implementation(project(":shared"))
            implementation(compose.components.resources)
        }
        val desktopMain by getting {
            dependencies {
                implementation(compose.desktop.currentOs)
                implementation(libs.kotlinx.coroutines.swing)
            }
        }
        androidMain.dependencies {
            implementation(libs.androidx.activity.compose)
            implementation(libs.androidx.work.runtime)
        }
    }
}

// Fonts bundled with the app (Liberation Serif – metric-compatible with Times New Roman, SIL Open Font License) for printed-style letters.
compose.resources {
    packageOfResClass = "zw.gov.chipingerdc.client.resources"
}

android {
    namespace = "zw.gov.chipingerdc.client"
    compileSdk = libs.versions.android.compileSdk.get().toInt()
    defaultConfig {
        applicationId = "zw.gov.chipingerdc.client"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "SERVER_URL", "\"${project.findProperty("councilServerUrl") ?: "http://10.0.2.2:8000"}\"")
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging { resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" } }
}

// Desktop application: ./gradlew :clientApp:run   ·   installers: ./gradlew :clientApp:packageDistributionForCurrentOS
compose.desktop {
    application {
        mainClass = "zw.gov.chipingerdc.client.MainKt"
        nativeDistributions {
            targetFormats(TargetFormat.Msi, TargetFormat.Exe, TargetFormat.Dmg, TargetFormat.Deb)
            packageName = "ChipingeRDC-Client"
            packageVersion = "1.0.0"
            description = "Chipinge RDC – Online services"
            vendor = "Chipinge Rural District Council"
            windows { menuGroup = "Chipinge RDC"; shortcut = true; perUserInstall = true }
        }
    }
}
