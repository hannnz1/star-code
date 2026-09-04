package com.starcode.prompt;

import com.starcode.agent.AgentMode;
import com.starcode.llm.TokenUsage;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SystemPromptEngineeringTest {
    @Test void modulesAreSortedAndEmptySlotsAreSkipped() {
        String result = SystemPromptAssembler.assemble(List.of(
                new PromptModule("low", 1, "low"), new PromptModule("empty", 2, "  "),
                new PromptModule("high", 3, "high")));
        assertEquals("high\n\nlow", result);
    }

    @Test void stablePromptIsDeterministicAndReinforcesRules() {
        String first = SystemPromptAssembler.assemble("identity");
        assertEquals(first, SystemPromptAssembler.assemble("identity"));
        assertTrue(first.contains("Prefer dedicated"));
        assertTrue(first.contains("Before editing a file, read"));
    }

    @Test void injectsInstructionsAndMemoryInDeclaredPriorityOrder() {
        String prompt = SystemPromptAssembler.assemble("identity", "PROJECT INSTRUCTIONS", "MEMORY INDEX");
        assertTrue(prompt.contains("PROJECT INSTRUCTIONS"));
        assertTrue(prompt.contains("MEMORY INDEX"));
        assertTrue(prompt.indexOf("PROJECT INSTRUCTIONS") < prompt.indexOf("MEMORY INDEX"));
        assertFalse(SystemPromptAssembler.assemble("identity", "", "").contains("PROJECT INSTRUCTIONS"));
    }

    @Test void skillsCatalogUsesStableOptionalModule() {
        String prompt = SystemPromptAssembler.assemble(
                "identity", "", "", "## Skills Catalog\n- review: Review code");
        assertTrue(prompt.contains("Skills Catalog"));
        assertTrue(prompt.indexOf("Skills Catalog") < prompt.indexOf("Use Markdown"));
    }

    @Test void planReminderUsesFullCompactAndPeriodicFullForms() {
        String first = SystemReminder.forTurn(AgentMode.PLAN, 1);
        String second = SystemReminder.forTurn(AgentMode.PLAN, 2);
        assertTrue(first.startsWith("<system-reminder>"));
        assertTrue(first.contains("produce a concrete plan"));
        assertFalse(second.contains("produce a concrete plan"));
        assertEquals(first, SystemReminder.forTurn(AgentMode.PLAN, 5));
        assertEquals("", SystemReminder.forTurn(AgentMode.DEFAULT, 1));
    }

    @Test void cacheUsageAccumulates() {
        assertEquals(new TokenUsage(13, 7, 11, 9),
                new TokenUsage(5, 3, 7, 2).plus(new TokenUsage(8, 4, 4, 7)));
    }
}
