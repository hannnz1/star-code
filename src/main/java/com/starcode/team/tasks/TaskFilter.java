package com.starcode.team.tasks;

import java.util.Optional;

public record TaskFilter(Optional<Status> status) {
    public TaskFilter { status = status == null ? Optional.empty() : status; }
    public static TaskFilter all() { return new TaskFilter(Optional.empty()); }
}
