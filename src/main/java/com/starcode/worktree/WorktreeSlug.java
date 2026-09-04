package com.starcode.worktree;

import java.util.regex.Pattern;

/** Validates user/model supplied names before they become paths or branches. */
public final class WorktreeSlug {
    private static final Pattern SEGMENT = Pattern.compile("^[A-Za-z0-9._-]+$");

    private WorktreeSlug() {}

    public static void validate(String name) {
        if (name == null || name.isBlank()) throw new IllegalArgumentException("Worktree 名称不能为空");
        if (name.length() > 64) throw new IllegalArgumentException("Worktree 名称不能超过 64 个字符");
        if (name.startsWith("/") || name.endsWith("/"))
            throw new IllegalArgumentException("Worktree 名称不能以 / 开头或结尾");
        if (name.contains("//")) throw new IllegalArgumentException("Worktree 名称不能包含空路径段");
        for (String part : name.split("/", -1)) {
            if (".".equals(part) || "..".equals(part))
                throw new IllegalArgumentException("Worktree 名称不能包含 . 或 .. 路径段");
            if (!SEGMENT.matcher(part).matches())
                throw new IllegalArgumentException("Worktree 名称包含非法字符: " + part);
        }
    }

    public static String flatten(String name) {
        validate(name);
        return name.replace('/', '+');
    }

    static String unflatten(String value) {
        return value.replace('+', '/');
    }
}
