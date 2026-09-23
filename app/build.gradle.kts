plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "com.bestintraday"
    compileSdk = 33

    defaultConfig {
        applicationId = "com.bestintraday"
        minSdk = 24
        targetSdk = 33
        versionCode = 3
        versionName = "3.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            install("pandas")
            install("requests")
            install("python-dateutil")
            install("lxml")
            install("kiteconnect")
        }
    }
}
