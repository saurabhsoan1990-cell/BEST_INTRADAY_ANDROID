plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "com.bestintraday"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.bestintraday"
        minSdk = 24
        targetSdk = 35
        versionCode = 2
        versionName = "2.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            install("pandas")
            install("requests")
            install("python-dateutil")
            install("lxml")
            install("kiteconnect")
        }
    }
}
