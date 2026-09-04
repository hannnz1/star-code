package com.starcode.team.backend;

public record SpawnRequest(
        String teamName,
        String memberName,
        String agentId,
        String worktreePath,
        String sessionDir,
        String agentType,
        String model,
        String initialPrompt,
        boolean planModeRequired,
        Object subAgent,
        Object conversation,
        Object taskManager) {}
