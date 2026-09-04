package com.starcode.command;

import java.util.*;

public record CommandSpec(String name, Set<String> aliases, String description,
                          CommandKind kind, boolean hidden, CommandSource source,
                          boolean acceptsArguments, CommandHandler handler) {
    public CommandSpec(String name, Set<String> aliases, String description,
                       CommandKind kind, boolean hidden, CommandHandler handler) {
        this(name, aliases, description, kind, hidden, CommandSource.BUILTIN, false, handler);
    }
    public CommandSpec(String name, Set<String> aliases, String description,
                       CommandKind kind, boolean hidden,
                       java.util.function.Consumer<CommandContext> handler) {
        this(name, aliases, description, kind, hidden, CommandSource.BUILTIN,
                false, (context, arguments) -> handler.accept(context));
    }
    public CommandSpec(String name, Set<String> aliases, String description,
                       CommandKind kind, boolean hidden, CommandSource source, CommandHandler handler) {
        this(name, aliases, description, kind, hidden, source, false, handler);
    }
    public CommandSpec {
        name = normalize(name);
        aliases = aliases == null ? Set.of() : aliases.stream()
                .map(CommandSpec::normalize).collect(java.util.stream.Collectors.toUnmodifiableSet());
        if (description == null || description.isBlank()) throw new IllegalArgumentException("Command description is required");
        Objects.requireNonNull(kind); Objects.requireNonNull(source); Objects.requireNonNull(handler);
    }
    public static CommandSpec visible(String name, String description, CommandKind kind, CommandHandler handler) {
        return new CommandSpec(name, Set.of(), description, kind, false, CommandSource.BUILTIN, false, handler);
    }
    public static CommandSpec withArguments(String name, String description, CommandKind kind, CommandHandler handler) {
        return new CommandSpec(name, Set.of(), description, kind, false, CommandSource.BUILTIN, true, handler);
    }
    public static CommandSpec skill(String name, String description, CommandHandler handler) {
        return new CommandSpec(name, Set.of(), description, CommandKind.PROMPT, false,
                CommandSource.SKILL, false, handler);
    }
    public static CommandSpec skill(String name, String description,
                                    java.util.function.Consumer<CommandContext> handler) {
        return skill(name, description, (context, arguments) -> handler.accept(context));
    }
    static String normalize(String value) {
        if (value == null || !value.matches("/[A-Za-z][A-Za-z0-9_-]*"))
            throw new IllegalArgumentException("Invalid command name: " + value);
        return value.toLowerCase(Locale.ROOT);
    }
}
