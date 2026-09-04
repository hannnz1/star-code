package com.starcode.command;

final class TeamCommand {
    private TeamCommand() {}

    static void execute(CommandContext context, String arguments) {
        String[] parts = arguments == null || arguments.isBlank()
                ? new String[0] : arguments.strip().split("\\s+");
        if (parts.length == 0) {
            context.notice("Usage: /team list | info <name> | delete <name> [--force]");
            return;
        }
        try {
            switch (parts[0].toLowerCase(java.util.Locale.ROOT)) {
                case "list" -> {
                    if (parts.length != 1) throw new IllegalArgumentException("Usage: /team list");
                    var teams = context.teams();
                    context.notice(teams.isEmpty() ? "No teams." : String.join("\n", teams));
                }
                case "info" -> {
                    if (parts.length != 2) throw new IllegalArgumentException("Usage: /team info <name>");
                    context.notice(context.teamInfo(parts[1]));
                }
                case "delete" -> {
                    if (parts.length < 2 || parts.length > 3)
                        throw new IllegalArgumentException("Usage: /team delete <name> [--force]");
                    boolean force = parts.length == 3 && "--force".equals(parts[2]);
                    if (parts.length == 3 && !force) throw new IllegalArgumentException("Unknown argument: " + parts[2]);
                    context.deleteTeam(parts[1], force);
                    context.notice("Team deleted: " + parts[1]);
                }
                default -> context.notice("Unknown team subcommand: " + parts[0]);
            }
        } catch (Exception error) {
            context.notice("Team operation failed: " + safe(error));
        }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
