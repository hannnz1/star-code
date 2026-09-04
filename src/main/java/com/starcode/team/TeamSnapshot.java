package com.starcode.team;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record TeamSnapshot(
        @JsonProperty("name") String name,
        @JsonProperty("description") String description,
        @JsonProperty("backend") BackendType backend,
        @JsonProperty("createdAt") long createdAt,
        @JsonProperty("members") List<TeammateInfo> members) {
    public TeamSnapshot {
        members = members == null ? List.of() : List.copyOf(members);
    }
}
