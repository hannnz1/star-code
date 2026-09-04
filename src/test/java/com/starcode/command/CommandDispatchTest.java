package com.starcode.command;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class CommandDispatchTest {
    @ParameterizedTest
    @CsvSource(value = {
            "<empty>|false|<empty>",
            "'   '|false|<empty>",
            "hello|false|<empty>",
            "/|true|<empty>",
            "/help|true|help",
            "'  /HELP  '|true|help",
            "'/help xx'|true|help",
            "'/help  '|true|help",
            "//double|true|<empty>",
            "'/ /help'|true|<empty>"
    }, delimiter = '|', nullValues = "<empty>")
    void parsesZeroArgumentCommands(String input, boolean slash, String name) {
        CommandDispatch.Parsed parsed = CommandDispatch.parse(input == null ? "" : input);
        assertEquals(slash, parsed.slashCommand());
        assertEquals(name == null ? "" : name, parsed.name());
        if ("/help xx".equals(input)) assertEquals("xx", parsed.arguments());
    }
}
