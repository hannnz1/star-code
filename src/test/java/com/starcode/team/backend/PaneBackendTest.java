package com.starcode.team.backend;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class PaneBackendTest {
    @Test void tmuxBuildsRunnerCommandAndReturnsPane() throws Exception {
        RecordingExecutor process = new RecordingExecutor("%7\n");
        TmuxBackend backend = new TmuxBackend(process, "java", "star code.jar");
        SpawnResult result = backend.spawn(request());
        assertEquals("%7", result.paneId());
        assertEquals("tmux", process.command.getFirst());
        String shellCommand = process.command.getLast();
        assertTrue(shellCommand.contains("--team-member"));
        assertTrue(shellCommand.contains("--team alpha"));
        assertTrue(shellCommand.contains("--prompt-base64"));
    }

    @Test void itermPassesArgumentsWithoutOneConcatenatedShellCommand() throws Exception {
        RecordingExecutor process = new RecordingExecutor("session-1\n");
        Iterm2Backend backend = new Iterm2Backend(process, "java", "app.jar");
        SpawnResult result = backend.spawn(request());
        assertEquals("session-1", result.paneId());
        assertEquals("it2", process.command.getFirst());
        assertTrue(process.command.contains("--team-member"));
        assertTrue(process.command.contains("alpha"));
    }

    @Test void memberArgumentsNeverExposeRawPrompt() {
        List<String> args = TeamMemberCommand.arguments(request());
        assertFalse(args.contains("secret prompt"));
        assertTrue(args.contains("--prompt-base64"));
    }

    private static SpawnRequest request() {
        return new SpawnRequest("alpha", "worker", "agent_1", Path.of(".").toAbsolutePath().toString(),
                Path.of("session").toAbsolutePath().toString(), "general-purpose", "inherit",
                "secret prompt", false, null, null, null);
    }

    private static final class RecordingExecutor implements ProcessExecutor {
        private final String output;
        private List<String> command = new ArrayList<>();
        private RecordingExecutor(String output) { this.output = output; }
        @Override public Result run(List<String> command, Path cwd) {
            this.command = List.copyOf(command);
            return new Result(0, output, "");
        }
    }
}
