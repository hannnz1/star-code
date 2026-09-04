package com.starcode.team;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.starcode.team.backend.BackendDetector;
import java.util.Map;
import org.junit.jupiter.api.Test;

class BackendDetectorTest {
    @Test void tmuxEnvironmentWinsAndEmptyEnvironmentFallsBack() {
        assertEquals(BackendType.TMUX, BackendDetector.detect(Map.of("TMUX", "socket"), ""));
        assertEquals(BackendType.IN_PROCESS, BackendDetector.detect(Map.of(), ""));
    }
}
