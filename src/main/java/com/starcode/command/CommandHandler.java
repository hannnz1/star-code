package com.starcode.command;

@FunctionalInterface
public interface CommandHandler {
    void execute(CommandContext context, String arguments);
}
