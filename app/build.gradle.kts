plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace = "com.zmad.sevensegment"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.zmad.sevensegment"
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
            isShrinkResources = true
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        viewBinding = true
    }
    dependenciesInfo {
        includeInApk = true
        includeInBundle = true
    }
    buildToolsVersion = "36.1.0"
    ndkVersion = "29.0.14206865"
}
