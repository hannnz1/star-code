package com.starcode.ui;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MarkdownRendererTest {
    @Test void rendersHeadingsCodeAndBold() {
        String result = MarkdownRenderer.render("# Title\n**bold** and `code`\n```java\nint x = 1;\n```");
        assertTrue(result.contains("Title"));
        assertTrue(result.contains("bold"));
        assertTrue(result.contains("int x = 1;"));
        assertTrue(result.contains("┌─ java"));
        assertTrue(result.contains("└─"));
    }

    @Test void rendersUnorderedListsAsBullets() {
        String result = MarkdownRenderer.render("- first\n* second\n1. ordered");
        assertTrue(result.contains("• first"));
        assertTrue(result.contains("• second"));
        assertTrue(result.contains("1. ordered"));
    }
}
