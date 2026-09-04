package com.starcode.command;

import java.util.Locale;

/** Parses a slash command name and preserves an optional raw argument tail. */
public final class CommandDispatch {
    private CommandDispatch() {}

    public record Parsed(String name, String arguments, boolean slashCommand) {}

    public static Parsed parse(String input) {
        String value = input == null ? "" : input.strip();
        if (!value.startsWith("/")) return new Parsed("", "", false);
        if (value.length() == 1) return new Parsed("", "", true);

        String body = value.substring(1);
        int whitespace = firstWhitespace(body);
        String arguments = "";
        if (whitespace >= 0) {
            arguments = body.substring(whitespace).strip();
            body = body.substring(0, whitespace);
        }
        if (body.isBlank() || body.startsWith("/")) return new Parsed("", "", true);
        return new Parsed(body.toLowerCase(Locale.ROOT), arguments, true);
    }

    private static int firstWhitespace(String value) {
        for (int i = 0; i < value.length(); i++) {
            if (Character.isWhitespace(value.charAt(i))) return i;
        }
        return -1;
    }
}
