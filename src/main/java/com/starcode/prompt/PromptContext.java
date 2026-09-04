package com.starcode.prompt;

import java.util.concurrent.atomic.AtomicReference;

public final class PromptContext {
    private final AtomicReference<String> instructions = new AtomicReference<>("");
    private final AtomicReference<String> memory = new AtomicReference<>("");
    private final AtomicReference<String> skillsCatalog = new AtomicReference<>("");
    private final AtomicReference<String> activeSkills = new AtomicReference<>("");
    public String instructions() { return instructions.get(); }
    public String memory() { return memory.get(); }
    public void instructions(String value) { instructions.set(value == null ? "" : value); }
    public void memory(String value) { memory.set(value == null ? "" : value); }
    public String skillsCatalog() { return skillsCatalog.get(); }
    public String activeSkills() { return activeSkills.get(); }
    public void skillsCatalog(String value) { skillsCatalog.set(value == null ? "" : value); }
    public void activeSkills(String value) { activeSkills.set(value == null ? "" : value); }
}
