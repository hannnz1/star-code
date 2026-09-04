package com.starcode.permission;

import java.util.Map;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ValueMatcherTest {
    @Test void permissionSyntaxSupportsExactRegexGlobAndNestedNot() {
        assertTrue(ValueMatchers.permission("=git status").matches("git status", false));
        assertFalse(ValueMatchers.permission("=git status").matches("git status -s", false));
        assertTrue(ValueMatchers.permission("~^npm (install|test)$").matches("npm test", false));
        assertFalse(ValueMatchers.permission("~^npm (install|test)$").matches("npm run dev", false));
        assertFalse(ValueMatchers.permission("!~^rm.*").matches("rm -rf .", false));
        assertTrue(ValueMatchers.permission("!~^rm.*").matches("ls -la", false));
        assertTrue(ValueMatchers.permission("src/**").matches("src/main/App.java", true));
    }

    @Test void structuredNotWrapsAnyMatcher() {
        ValueMatcher matcher = ValueMatchers.structured(Map.of(
                "type", "not", "inner", Map.of("type", "exact", "value", "secret")));
        assertFalse(matcher.matches("secret", false));
        assertTrue(matcher.matches("public", false));
    }

    @Test void invalidRegexAndMissingInnerFailAtLoadTime() {
        assertThrows(RuleParseException.class, () -> ValueMatchers.permission("~["));
        assertThrows(RuleParseException.class, () -> ValueMatchers.structured(Map.of("type", "not")));
    }
}
