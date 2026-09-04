package com.starcode.skill;

import static org.junit.jupiter.api.Assertions.*;

import java.io.IOException;
import org.junit.jupiter.api.Test;

class GitHubSkillInstallerTest {
    @Test void parsesApprovedGitHubUrls() throws Exception {
        GitHubSkillInstaller.Source tree = GitHubSkillInstaller.parse(
                "https://github.com/acme/skills/tree/main/review-java");
        assertEquals("acme", tree.owner()); assertEquals("skills", tree.repo());
        assertEquals("main", tree.ref()); assertEquals("review-java", tree.path());
        assertEquals("review-java", tree.skillName());

        GitHubSkillInstaller.Source raw = GitHubSkillInstaller.parse(
                "https://raw.githubusercontent.com/acme/skills/main/review-java/SKILL.md");
        assertEquals("review-java", raw.path()); assertEquals("review-java", raw.skillName());
    }

    @Test void rejectsUnapprovedOrUnsafeUrls() {
        assertThrows(IOException.class, () -> GitHubSkillInstaller.parse("http://github.com/a/b/tree/main/skill"));
        assertThrows(IOException.class, () -> GitHubSkillInstaller.parse("https://example.com/a/b/tree/main/skill"));
        assertThrows(IOException.class, () -> GitHubSkillInstaller.parse("https://github.com/a/b/tree/main/../skill"));
        assertThrows(IOException.class, () -> GitHubSkillInstaller.parse("https://user@github.com/a/b/tree/main/skill"));
    }
}
