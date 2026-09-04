package com.starcode.instructions;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class InstructionLoaderTest {
    @TempDir Path temp;

    @Test void loadsThreeLayersInPriorityOrderAndExpandsIncludes() throws Exception {
        Path project = Files.createDirectories(temp.resolve("project"));
        Path user = Files.createDirectories(temp.resolve("user"));
        Files.createDirectories(project.resolve(".mewcode"));
        Files.createDirectories(project.resolve("rules"));
        Files.writeString(project.resolve("rules/style.md"), "included style");
        Files.writeString(project.resolve("MEWCODE.md"), "project root\n@include rules/style.md");
        Files.writeString(project.resolve(".mewcode/MEWCODE.md"), "project config");
        Files.writeString(user.resolve("MEWCODE.md"), "user rules");

        String result = new InstructionLoader(project, user).load();

        assertTrue(result.indexOf("project root") < result.indexOf("project config"));
        assertTrue(result.indexOf("project config") < result.indexOf("user rules"));
        assertTrue(result.contains("included style"));
        assertFalse(result.contains("@include rules/style.md"));
    }

    @Test void detectsCycleDepthAndPathEscape() throws Exception {
        Path project = Files.createDirectories(temp.resolve("project"));
        Path user = Files.createDirectories(temp.resolve("user"));
        Files.writeString(project.resolve("MEWCODE.md"), "@include a.md\n@include ../outside.md");
        Files.writeString(project.resolve("a.md"), "@include b.md");
        Files.writeString(project.resolve("b.md"), "@include a.md");
        Files.writeString(temp.resolve("outside.md"), "secret");

        String result = new InstructionLoader(project, user).load();

        assertTrue(result.contains("检测到环路"));
        assertTrue(result.contains("路径超出允许范围"));
        assertFalse(result.contains("secret"));

        for (int i = 1; i <= 6; i++) {
            Files.writeString(project.resolve("d" + i + ".md"), i == 6 ? "deep" : "@include d" + (i + 1) + ".md");
        }
        Files.writeString(project.resolve("MEWCODE.md"), "@include d1.md");
        assertTrue(new InstructionLoader(project, user).load().contains("超过最大嵌套深度"));
    }
}
