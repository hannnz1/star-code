package com.starcode.skill;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SkillCatalogTest {
    @TempDir Path temp;

    @Test void discoversMetadataLazilyAndReloadsBodyOnEveryGetFull() throws Exception {
        Path skill = Files.createDirectories(temp.resolve("review"));
        Files.writeString(skill.resolve("SKILL.md"), """
                ---
                name: review
                description: Review the current implementation
                tags: [java, quality]
                mode: inline
                ---
                First body
                """);
        SkillCatalog catalog = new SkillCatalog();
        catalog.loadFromDirectory(temp);
        Skill metadata = catalog.get("review").orElseThrow();
        assertFalse(metadata.bodyLoaded());
        assertEquals("", metadata.promptBody());
        assertEquals("Review the current implementation", metadata.meta().description());

        assertEquals("First body", catalog.getFull("review").orElseThrow().promptBody().strip());
        Files.writeString(skill.resolve("SKILL.md"), """
                ---
                name: review
                description: Review the current implementation
                ---
                Updated body
                """);
        assertEquals("Updated body", catalog.getFull("review").orElseThrow().promptBody().strip());
    }

    @Test void supportsYamlPromptFormatAndLaterRegistrationWins() throws Exception {
        Path skill = Files.createDirectories(temp.resolve("commit helper"));
        Files.writeString(skill.resolve("skill.yaml"), """
                description: Prepare a commit
                mode: fork
                provider: alternate
                fork_context: recent
                """);
        Files.writeString(skill.resolve("prompt.md"), "\uFEFFPrepare commit: $ARGUMENTS");
        SkillCatalog catalog = new SkillCatalog();
        catalog.loadFromDirectory(temp);
        Skill loaded = catalog.getFull("commit-helper").orElseThrow();
        assertTrue(loaded.meta().fork());
        assertEquals("alternate", loaded.meta().provider());
        assertEquals("recent", loaded.meta().forkContext());
        assertEquals("Prepare commit: $ARGUMENTS", loaded.promptBody());

        Skill replacement = new Skill(new SkillMeta("commit-helper", "project override", "",
                java.util.List.of(), "inline", "", "none"), "override", null, SkillSource.PROJECT, true);
        catalog.register(replacement);
        assertEquals("project override", catalog.get("commit-helper").orElseThrow().meta().description());
    }

    @Test void skipsInvalidSkillWithoutLosingValidSibling() throws Exception {
        Files.createDirectories(temp.resolve("broken"));
        Path good = Files.createDirectories(temp.resolve("good"));
        Files.writeString(good.resolve("SKILL.md"), "# Useful skill\n\nDo useful work.");
        SkillCatalog catalog = new SkillCatalog();
        catalog.loadFromDirectory(temp);
        assertEquals(1, catalog.list().size());
        assertTrue(catalog.get("good").isPresent());
    }

    @Test void acceptsUtf8BomWrittenByWindowsPowerShell() throws Exception {
        Path skill = Files.createDirectories(temp.resolve("powershell-skill"));
        Files.writeString(skill.resolve("SKILL.md"), "\uFEFF" + """
                ---
                name: powershell-skill
                description: PowerShell UTF-8 skill
                ---
                Reply with success.
                """);
        SkillCatalog catalog = new SkillCatalog();
        catalog.loadFromDirectory(temp);
        Skill loaded = catalog.getFull("powershell-skill").orElseThrow();
        assertEquals("PowerShell UTF-8 skill", loaded.meta().description());
        assertEquals("Reply with success.", loaded.promptBody().strip());
    }
}
