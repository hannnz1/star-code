package com.starcode.command;

import com.starcode.llm.TokenUsage;
import java.nio.file.Path;
import java.util.List;

public interface CommandContext {
    void notice(String message);
    void requestExit();
    void enterPlanMode();
    void enterDefaultMode();
    void sendPrompt(String prompt);
    void compactContext();
    void resumeSession();
    void clearSession();
    default void rewind(String arguments) { notice("File checkpoints are unavailable in this context."); }
    String permissionMode();
    TokenUsage tokenUsage();
    int toolCount();
    List<String> projectMemoryFiles();
    List<String> userMemoryFiles();
    String modelName();
    Path workspace();
    String sessionId();
    Path sessionFile();
    List<String> catalogSkills();
    List<String> activeSkillNames();
    void reloadSkills();
    String hooksReport();
    default WorktreeAccessor worktrees() { return null; }
    default List<String> teams() { return List.of(); }
    default String teamInfo(String name) { return "Team support is unavailable."; }
    default void deleteTeam(String name, boolean force) { throw new IllegalStateException("Team support is unavailable"); }
}
