plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "uk.mygov.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "uk.mygov.mobile"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    // Signing config reads from env vars injected by CI or -P Gradle properties.
    // Never hard-code credentials — see docs/release.md.
    val keystorePath     = System.getenv("KEYSTORE_PATH")
        ?: findProperty("android.injected.signing.store.file")?.toString()
    val keystorePassword = System.getenv("KEYSTORE_PASSWORD")
        ?: findProperty("android.injected.signing.store.password")?.toString()
    val keyAlias         = System.getenv("KEY_ALIAS")
        ?: findProperty("android.injected.signing.key.alias")?.toString()
    val keyPassword      = System.getenv("KEY_PASSWORD")
        ?: findProperty("android.injected.signing.key.password")?.toString()

    if (keystorePath != null) {
        signingConfigs {
            create("release") {
                storeFile     = file(keystorePath)
                storePassword = keystorePassword ?: ""
                this.keyAlias = keyAlias ?: "mygov"
                keyPassword   = keyPassword ?: ""
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled   = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            if (keystorePath != null) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
        debug {
            applicationIdSuffix = ".debug"
            isDebuggable         = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    buildFeatures {
        viewBinding = true
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.activity:activity-ktx:1.9.3")
}
