package com.starcode.command;

import java.util.List;

/** UI-independent state for the slash-command completion menu. */
public final class CommandCompletion {
    public static final int MAX_ROWS = 8;

    private List<CommandSpec> items = List.of();
    private int cursor;
    private int offset;
    private boolean active;
    private String input = "";

    public void update(String input, CommandRegistry registry) {
        if (input == null || input.indexOf('\n') >= 0 || !input.startsWith("/")) {
            hide();
            return;
        }
        boolean changed = !this.input.equals(input);
        this.input = input;
        active = true;
        items = registry.complete(input);
        if (changed) { cursor = 0; offset = 0; }
        cursor = items.isEmpty() ? 0 : Math.min(cursor, items.size() - 1);
        keepCursorVisible();
    }

    public void moveUp() {
        if (items.isEmpty()) return;
        cursor = Math.floorMod(cursor - 1, items.size());
        keepCursorVisible();
    }

    public void moveDown() {
        if (items.isEmpty()) return;
        cursor = (cursor + 1) % items.size();
        keepCursorVisible();
    }

    public CommandSpec selected() {
        return items.isEmpty() ? null : items.get(cursor);
    }

    public List<CommandSpec> visibleItems() {
        int end = Math.min(items.size(), offset + MAX_ROWS);
        return items.subList(Math.min(offset, end), end);
    }

    public List<CommandSpec> items() { return items; }
    public int cursor() { return cursor; }
    public int offset() { return offset; }
    public boolean active() { return active; }

    public void hide() {
        active = false;
        items = List.of();
        cursor = 0;
        offset = 0;
        input = "";
    }

    private void keepCursorVisible() {
        if (cursor < offset) offset = cursor;
        if (cursor >= offset + MAX_ROWS) offset = cursor - MAX_ROWS + 1;
        int maximum = Math.max(0, items.size() - MAX_ROWS);
        offset = Math.min(offset, maximum);
    }
}
