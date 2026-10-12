import java.util.Properties

plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// 签名信息从 keystore.properties 读取；文件缺失时只产出未签名的 APK，
// 以免构建脚本因为缺少密钥而失败。
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) keystorePropsFile.inputStream().use { load(it) }
}
val hasKeystore = keystoreProps.getProperty("storeFile") != null

android {
    namespace = "com.calorietracker.app"
    compileSdk = 35
    // 显式指定构建工具版本，避免 AGP 去请求它默认的 34.0.0（本机只装了 35.0.0）。
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "com.calorietracker.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1beta"

        ndk {
            // 只打包 arm64-v8a，减小体积。
            abiFilters += "arm64-v8a"
        }
    }

    if (hasKeystore) {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // 体积几乎全部来自 Python 运行时，压缩 Java 代码收益很小，
            // 关掉 R8/资源压缩以降低构建风险。
            isMinifyEnabled = false
            isShrinkResources = false
            if (hasKeystore) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
        debug {
            applicationIdSuffix = ".debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }

    lint {
        abortOnError = false
    }
}

chaquopy {
    defaultConfig {
        version = "3.14"
        // 没有第三方依赖，但仍然显式指定源码目录。
        sourceSets {
            getByName("main") {
                srcDir("src/main/python")
            }
        }
        // 未使用 pip 依赖：后端只用 Python 标准库。
        pip {
            // 留空表示不安装任何第三方包。
        }
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core:1.13.1")
    implementation("androidx.activity:activity:1.9.3")
}

// appcompat / core 会传递引入 kotlin-stdlib-jdk7/jdk8 1.6.x，与 kotlin-stdlib 1.8.x
// 产生重复类（checkReleaseDuplicateClasses 报 Duplicate class kotlin.*）。
// 1.8 起 jdk7/jdk8 的内容已合并进 kotlin-stdlib，因此统一版本即可。
configurations.configureEach {
    resolutionStrategy {
        force("org.jetbrains.kotlin:kotlin-stdlib:1.8.22")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.8.22")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.8.22")
    }
}
