plugins {
    alias(libs.plugins.android.application)
}

// Declared here rather than in settings.gradle.kts, where the repositories API is still @Incubating.
// AGP resolves build tooling (e.g. aapt2) from these.
repositories {
    google()
    mavenCentral()
}

android {
    namespace = "dev.zachmaddox.watchface.sevensegment"
    compileSdk = 37

    defaultConfig {
        applicationId = "dev.zachmaddox.watchface.sevensegment"
        // Watch Face Format v2 requires Wear OS 5 (API 34) or newer.
        minSdk = 34
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            // There is no code to keep, so R8 strips the generated R class and leaves a dex-free APK.
            isMinifyEnabled = true
            // Safe only because res/raw/keep.xml keeps the resources the watch face runtime loads by name.
            isShrinkResources = true
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    dependenciesInfo {
        includeInApk = true
        includeInBundle = true
    }
    buildToolsVersion = "36.1.0"
    ndkVersion = "29.0.14206865"
}
