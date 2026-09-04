plugins {
    java
    application
    id("com.gradleup.shadow") version "8.3.6"
}

group = "com.starcode"
version = "0.1.0"

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

application { mainClass = "com.starcode.Main" }

repositories { mavenCentral() }

dependencies {
    implementation(platform("io.modelcontextprotocol.sdk:mcp-bom:2.0.1"))
    implementation("io.modelcontextprotocol.sdk:mcp-core")
    implementation("io.modelcontextprotocol.sdk:mcp-json-jackson2")
    runtimeOnly("org.slf4j:slf4j-nop:2.0.17")
    implementation("org.jline:jline:3.30.6")
    implementation("org.jline:jline-terminal-jni:3.30.6")
    implementation("org.yaml:snakeyaml:2.4")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.20.1")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.withType<JavaCompile> { options.encoding = "UTF-8"; options.compilerArgs.add("-Xlint:deprecation") }
tasks.test { useJUnitPlatform() }
tasks.shadowJar {
    archiveBaseName = "star-code"
    archiveClassifier = ""
    archiveVersion = ""
    mergeServiceFiles()
}
