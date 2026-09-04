package com.starcode.team.tasks;

import java.util.List;
import java.util.Optional;

public record TaskPatch(
        Optional<String> title,
        Optional<String> description,
        Optional<Status> status,
        Optional<String> assignee,
        List<String> addBlocks,
        List<String> addBlockedBy,
        List<String> removeBlocks,
        List<String> removeBlockedBy) {
    public TaskPatch {
        title = title == null ? Optional.empty() : title;
        description = description == null ? Optional.empty() : description;
        status = status == null ? Optional.empty() : status;
        assignee = assignee == null ? Optional.empty() : assignee;
        addBlocks = addBlocks == null ? List.of() : List.copyOf(addBlocks);
        addBlockedBy = addBlockedBy == null ? List.of() : List.copyOf(addBlockedBy);
        removeBlocks = removeBlocks == null ? List.of() : List.copyOf(removeBlocks);
        removeBlockedBy = removeBlockedBy == null ? List.of() : List.copyOf(removeBlockedBy);
    }

    public static TaskPatch empty() {
        return new TaskPatch(Optional.empty(), Optional.empty(), Optional.empty(), Optional.empty(),
                List.of(), List.of(), List.of(), List.of());
    }
}
