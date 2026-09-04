package com.starcode.team;

import com.fasterxml.jackson.annotation.JsonProperty;

public record TeammateInfo(
        @JsonProperty("name") String name,
        @JsonProperty("agentId") String agentId,
        @JsonProperty("agentType") String agentType,
        @JsonProperty("model") String model,
        @JsonProperty("backendType") BackendType backendType,
        @JsonProperty("paneId") String paneId,
        @JsonProperty("worktreePath") String worktreePath,
        @JsonProperty("sessionDir") String sessionDir,
        @JsonProperty("active") boolean active) {

    public TeammateInfo withActive(boolean value) {
        return new TeammateInfo(name, agentId, agentType, model, backendType, paneId,
                worktreePath, sessionDir, value);
    }
}
