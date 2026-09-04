package com.starcode.skill;

import java.util.*;

public final class ActiveSkills {
    public record Entry(String name, String body) {}
    private final LinkedHashMap<String, Entry> entries = new LinkedHashMap<>();

    public synchronized void activate(String name, String body) {
        entries.put(name, new Entry(name, body));
    }
    public synchronized void clear() { entries.clear(); }
    public synchronized List<Entry> snapshot() { return List.copyOf(entries.values()); }
    public synchronized List<String> names() { return List.copyOf(entries.keySet()); }

    public synchronized String render() {
        if (entries.isEmpty()) return "";
        StringBuilder value = new StringBuilder("## Active Skills\n");
        entries.values().forEach(entry -> value.append("\n### Skill: ").append(entry.name())
                .append("\n\n").append(entry.body().strip()).append('\n'));
        return value.toString().strip();
    }
}
