package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.team.tasks.Status;
import com.starcode.team.tasks.TaskFilter;
import com.starcode.team.tasks.TaskPatch;
import com.starcode.team.tasks.TeamTaskStore;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TeamTaskStoreTest {
    @TempDir Path temp;

    @Test void createsFiltersAndMaintainsDependencyGraph() throws Exception {
        TeamTaskStore store = new TeamTaskStore(temp.resolve("tasks.json"));
        String first = store.create("first", "", "alice", List.of());
        String second = store.create("second", "", "bob", List.of(first));
        assertTrue(first.matches("task_[0-9a-f]{6}"));
        assertEquals(List.of(second), store.get(first).orElseThrow().blocks());
        assertEquals(List.of(first), store.get(second).orElseThrow().blockedBy());
        assertFalse(store.list(TaskFilter.all()).stream()
                .filter(view -> view.task().id().equals(second)).findFirst().orElseThrow().isReady());
        store.update(first, new TaskPatch(Optional.empty(), Optional.empty(), Optional.of(Status.COMPLETED),
                Optional.empty(), List.of(), List.of(), List.of(), List.of()));
        assertTrue(store.list(new TaskFilter(Optional.of(Status.PENDING))).stream()
                .filter(view -> view.task().id().equals(second)).findFirst().orElseThrow().isReady());
    }
}
