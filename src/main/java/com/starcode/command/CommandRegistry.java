package com.starcode.command;

import java.util.*;

public final class CommandRegistry {
    private final Map<String, CommandSpec> lookup = new LinkedHashMap<>();
    private final List<CommandSpec> commands = new ArrayList<>();

    public CommandRegistry register(CommandSpec command) {
        Objects.requireNonNull(command);
        Set<String> ownKeys = new HashSet<>();
        for (String key : keys(command)) {
            if (!ownKeys.add(key)) throw new IllegalArgumentException("Slash command name or alias conflict: " + key);
            CommandSpec existing = lookup.get(key);
            if (existing != null) throw new IllegalArgumentException(
                    "Slash command name or alias conflict: " + key + " (" + existing.name() + " vs " + command.name() + ")");
        }
        commands.add(command);
        for (String key : keys(command)) lookup.put(key, command);
        return this;
    }

    public synchronized void removeBySource(CommandSource source) {
        commands.removeIf(command -> command.source() == source);
        lookup.clear();
        for (CommandSpec command : commands) {
            for (String key : keys(command)) lookup.put(key, command);
        }
    }

    public Optional<CommandSpec> resolve(String submitted) {
        CommandDispatch.Parsed parsed = CommandDispatch.parse(submitted);
        if (!parsed.slashCommand() || parsed.name().isEmpty()) return Optional.empty();
        CommandSpec found = lookup.get("/" + parsed.name());
        if (found == null || (!parsed.arguments().isBlank() && !found.acceptsArguments())) return Optional.empty();
        return Optional.of(found);
    }

    public boolean dispatch(String submitted, CommandContext context) {
        Optional<CommandSpec> found = resolve(submitted);
        if (found.isEmpty()) return false;
        found.get().handler().execute(context, CommandDispatch.parse(submitted).arguments()); return true;
    }

    public List<CommandSpec> visibleCommands() {
        return commands.stream().filter(command -> !command.hidden())
                .sorted(Comparator.comparing(CommandSpec::name)).toList();
    }

    public List<CommandSpec> complete(String prefix) {
        String normalized = prefix == null ? "" : prefix.toLowerCase(Locale.ROOT);
        if (!normalized.startsWith("/") || normalized.indexOf('\n') >= 0) return List.of();
        return visibleCommands().stream().filter(command -> command.name().startsWith(normalized)).toList();
    }

    public String helpText() {
        int width = visibleCommands().stream().mapToInt(command -> command.name().length()).max().orElse(0);
        return visibleCommands().stream()
                .map(command -> String.format("%-" + width + "s  %s", command.name(), command.description()))
                .reduce((left, right) -> left + "\n" + right).orElse("");
    }

    private static List<String> keys(CommandSpec command) {
        List<String> keys = new ArrayList<>(); keys.add(command.name()); keys.addAll(command.aliases()); return keys;
    }
}
