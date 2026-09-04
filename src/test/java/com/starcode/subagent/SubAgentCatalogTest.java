package com.starcode.subagent;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SubAgentCatalogTest {
    @TempDir Path temp;

    @Test void loadsBuiltinsAndProjectOverridesUserCaseInsensitively() throws Exception {
        Path home = temp.resolve("home");
        Path project = temp.resolve("project");
        Files.createDirectories(home.resolve(".mewcode/agents"));
        Files.createDirectories(project.resolve(".mewcode/agents"));
        Files.writeString(home.resolve(".mewcode/agents/explore.md"), definition("Explore", "user"));
        Files.writeString(project.resolve(".mewcode/agents/explore.md"), definition("explore", "project"));
        SubAgentCatalog catalog = SubAgentCatalog.load(project, home);
        assertEquals(3, catalog.list().size());
        SubAgentDefinition value = catalog.resolve("EXPLORE").orElseThrow();
        assertEquals(SubAgentSource.PROJECT, value.source());
        assertEquals("project", value.description());
        assertTrue(catalog.forkDefinition().fork());
    }

    @Test void badUserDefinitionDoesNotHideBuiltins() throws Exception {
        Path home = temp.resolve("home2");
        Path project = temp.resolve("project2");
        Files.createDirectories(home.resolve(".mewcode/agents"));
        Files.createDirectories(project);
        Files.writeString(home.resolve(".mewcode/agents/bad.md"), "---\nname: bad name\n---\nbody");
        SubAgentCatalog catalog = SubAgentCatalog.load(project, home);
        assertTrue(catalog.resolve("general-purpose").isPresent());
        assertTrue(catalog.resolve("explore").isPresent());
        assertTrue(catalog.resolve("plan").isPresent());
    }

    private static String definition(String name, String description) {
        return "---\nname: " + name + "\ndescription: " + description + "\n---\nbody";
    }
}
