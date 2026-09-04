package com.starcode.command;

import java.util.Arrays;

final class WorktreeCommand {
    private WorktreeCommand() {}

    static void execute(CommandContext context, String arguments) {
        WorktreeAccessor accessor = context.worktrees();
        if (accessor == null) {
            context.notice("Worktree 功能未启用：当前工作目录必须是已有提交的 Git 仓库");
            return;
        }
        String[] parts = arguments == null || arguments.isBlank()
                ? new String[0] : arguments.strip().split("\\s+");
        if (parts.length == 0) {
            context.notice("用法: /worktree create <slug> | list | enter <slug> | exit [--remove] [--discard] | remove <slug> [--discard]");
            return;
        }
        try {
            switch (parts[0].toLowerCase(java.util.Locale.ROOT)) {
                case "create" -> create(context, accessor, parts);
                case "list" -> list(context, accessor, parts);
                case "enter" -> enter(context, accessor, parts);
                case "exit" -> exit(context, accessor, parts);
                case "remove" -> remove(context, accessor, parts);
                default -> context.notice("未知 Worktree 子命令: " + parts[0]);
            }
        } catch (Exception error) {
            context.notice("Worktree 操作失败: " + safe(error));
        }
    }

    private static void create(CommandContext context, WorktreeAccessor accessor, String[] parts) throws Exception {
        requireCount(parts, 2, "用法: /worktree create <slug>");
        WorktreeAccessor.CreateResult value = accessor.create(parts[1]);
        context.notice("Worktree 已创建: " + value.path() + " (分支 " + value.branch() + ")");
    }

    private static void list(CommandContext context, WorktreeAccessor accessor, String[] parts) {
        if (parts.length != 1) throw new IllegalArgumentException("用法: /worktree list");
        var values = accessor.list();
        if (values.isEmpty()) { context.notice("没有已管理的 Worktree"); return; }
        context.notice(values.stream().map(value -> value.name() + "  " + value.path() + "  " + value.branch()
                + (value.active() ? " [active]" : "") + (value.manual() ? " [manual]" : " [temporary]"))
                .reduce((left, right) -> left + "\n" + right).orElse(""));
    }

    private static void enter(CommandContext context, WorktreeAccessor accessor, String[] parts) throws Exception {
        requireCount(parts, 2, "用法: /worktree enter <slug>");
        WorktreeAccessor.EnterResult value = accessor.enter(parts[1]);
        context.notice("已进入 Worktree " + value.name() + ": " + value.path());
    }

    private static void exit(CommandContext context, WorktreeAccessor accessor, String[] parts) throws Exception {
        boolean remove = flag(parts, "--remove"), discard = flag(parts, "--discard");
        rejectUnknownFlags(parts, 1, "--remove", "--discard");
        if (discard && !remove) throw new IllegalArgumentException("--discard 只能与 --remove 一起使用");
        WorktreeAccessor.ExitResult value = accessor.exit(remove, discard);
        context.notice(value.removed() ? "已退出并删除 Worktree: " + value.path()
                : "已退出 Worktree，目录保留: " + value.path());
    }

    private static void remove(CommandContext context, WorktreeAccessor accessor, String[] parts) throws Exception {
        if (parts.length < 2 || parts.length > 3)
            throw new IllegalArgumentException("用法: /worktree remove <slug> [--discard]");
        rejectUnknownFlags(parts, 2, "--discard");
        WorktreeAccessor.ExitResult value = accessor.remove(parts[1], flag(parts, "--discard"));
        context.notice("已删除 Worktree: " + value.path());
    }

    private static boolean flag(String[] parts, String value) {
        return Arrays.asList(parts).contains(value);
    }

    private static void rejectUnknownFlags(String[] parts, int from, String... allowed) {
        var valid = java.util.Set.of(allowed);
        for (int i = from; i < parts.length; i++)
            if (!valid.contains(parts[i])) throw new IllegalArgumentException("未知参数: " + parts[i]);
    }

    private static void requireCount(String[] values, int count, String message) {
        if (values.length != count) throw new IllegalArgumentException(message);
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }
}
