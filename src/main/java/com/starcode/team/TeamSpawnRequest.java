package com.starcode.team;

public record TeamSpawnRequest(
        String teamName,
        String subagentType,
        String memberName,
        String prompt,
        String description,
        String model) {}
