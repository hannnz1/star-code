package com.starcode.command;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class CommandCompletionTest {
    @Test void filtersMovesAndHides() {
        CommandRegistry registry = BuiltinCommands.create();
        CommandCompletion completion = new CommandCompletion();
        completion.update("/s", registry);
        assertTrue(completion.active());
        assertEquals(List.of("/session", "/skill", "/status"),
                completion.items().stream().map(CommandSpec::name).toList());
        assertEquals("/session", completion.selected().name());
        completion.moveDown();
        assertEquals("/skill", completion.selected().name());
        completion.moveUp();
        assertEquals("/session", completion.selected().name());
        completion.update("normal", registry);
        assertFalse(completion.active());
    }

    @Test void staysActiveForNoMatchesAndRejectsMultiline() {
        CommandCompletion completion = new CommandCompletion();
        completion.update("/status extra", BuiltinCommands.create());
        assertTrue(completion.active());
        assertNull(completion.selected());
        completion.update("/status", BuiltinCommands.create());
        assertEquals("/status", completion.selected().name());
        completion.update("/status\nextra", BuiltinCommands.create());
        assertFalse(completion.active());
    }
}
