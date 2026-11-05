plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

// The task code is shared with the desktop app: copy it from the repository root instead
// of keeping a second copy (ui/ only contributes its Qt-free modules).
val repoRoot: File = rootProject.projectDir.parentFile
val sharedPython = layout.buildDirectory.dir("generated/sharedPython")
val sharedAssets = layout.buildDirectory.dir("generated/sharedAssets")

val syncSharedPython by tasks.registering(Sync::class) {
    from(repoRoot) {
        include("main.py", "api/*.py", "core/*.py", "ui/output_parser.py", "ui/advanced.py", "ui/cloudmodels.py")
    }
    into(sharedPython)
}

// Data files the task code opens by path (resource/font_map_table.json); copied out of the
// APK into the app's files directory at start, see PythonBridge.kt.
val syncSharedAssets by tasks.registering(Sync::class) {
    from(repoRoot) { include("resource/*.json", "config_template.ini") }
    into(sharedAssets)
}

android {
    namespace = "io.github.kerxs.xxtplus"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.kerxs.xxtplus"
        minSdk = 24
        targetSdk = 35
        versionCode = 10204
        versionName = "1.2.4"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    // Release key: never in the repository. Set xxtplus.storeFile / storePassword / keyAlias /
    // keyPassword in %USERPROFILE%\.gradle\gradle.properties. Every update must be signed with the
    // same key, or phones refuse to install it over the previous version.
    val releaseStore = providers.gradleProperty("xxtplus.storeFile").orNull
    signingConfigs {
        if (releaseStore != null) {
            create("release") {
                storeFile = file(releaseStore)
                storePassword = providers.gradleProperty("xxtplus.storePassword").get()
                keyAlias = providers.gradleProperty("xxtplus.keyAlias").get()
                keyPassword = providers.gradleProperty("xxtplus.keyPassword").get()
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Without the release key (e.g. on another machine) fall back to the debug key.
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }

    sourceSets["main"].assets.srcDir(sharedAssets.get().asFile)

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        // Default: Chaquopy finds Python 3.13 itself (`py -3.13` on Windows). The embeddable
        // Python in ..\.build cannot be used: it has no venv module.
        providers.gradleProperty("xxtplus.buildPython").orNull?.let { buildPython(it) }
        pip {
            // requirements-desktop.txt minus:
            //  - openai: needs pydantic-core / jiter, which have no Android builds; a small
            //    compatible client is in src/main/python/openai
            //  - ddddocr: onnxruntime has no Android build; captcha OCR is unavailable
            //    (api/captcha.py already handles the missing module)
            install("requests")
            install("pyaes")
            install("beautifulsoup4")
            install("lxml")
            install("loguru")
            install("fonttools")
            install("tqdm")
            install("httpx[socks]")
            install("urllib3")
            install("tenacity")
            install("typing_extensions")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir("src/main/python")
            srcDir(sharedPython.get().asFile)
        }
    }
}

tasks.named("preBuild") { dependsOn(syncSharedPython, syncSharedAssets) }
tasks.matching { it.name.contains("Python", ignoreCase = false) && it.name.startsWith("merge") }
    .configureEach { dependsOn(syncSharedPython) }

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
