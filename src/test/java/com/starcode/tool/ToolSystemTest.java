package com.starcode.tool;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.starcode.agent.CancellationToken;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.Set;
import java.time.Duration;
import java.util.stream.Collectors;
import static org.junit.jupiter.api.Assertions.*;

class ToolSystemTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path temp;
    private ToolRegistry registry;
    private ToolContext context;

    @BeforeEach void setUp() throws Exception {
        registry = ToolRegistry.standard(); context = new ToolContext(temp, true, true);
    }

    @Test void registersSixTools() {
        assertEquals(6, registry.count());
        assertEquals(Set.of("read_file", "write_file", "edit_file", "bash", "glob", "search_text"),
                registry.definitions().stream().map(ToolDefinition::name).collect(Collectors.toSet()));
    }

    @Test void mutationsAreDisabledByDefaultContext() throws Exception {
        ToolContext safe = new ToolContext(temp, false, false);
        ToolResult write = registry.execute(new ToolCall("w", "write_file", args("path", "x", "content", "x")), safe);
        ToolResult bash = registry.execute(new ToolCall("b", "bash", args("command", "Write-Output x")), safe);
        assertEquals("WRITE_DISABLED", write.errorCode()); assertEquals("BASH_DISABLED", bash.errorCode());
    }

    @Test void writesNestedFileAndReadsWithLineNumbers() {
        ToolResult write = execute("write_file", args("path", "nested/test.txt", "content", "alpha\nbeta"));
        assertTrue(write.success(), write.modelText());
        ToolResult read = execute("read_file", args("path", "nested/test.txt"));
        assertTrue(read.success()); assertTrue(read.output().contains("1 | alpha")); assertTrue(read.output().contains("2 | beta"));
    }

    @Test void rejectsWorkspaceEscapeAndMissingFile() {
        ToolResult escape = execute("write_file", args("path", "../outside.txt", "content", "bad"));
        assertFalse(escape.success()); assertFalse(Files.exists(temp.getParent().resolve("outside.txt")));
        ToolResult missing = execute("read_file", args("path", "missing.txt"));
        assertFalse(missing.success()); assertEquals("NOT_FOUND", missing.errorCode());
    }

    @Test void editRequiresExactlyOneMatch() throws Exception {
        Files.writeString(temp.resolve("one.txt"), "before");
        assertTrue(execute("edit_file", args("path", "one.txt", "old_text", "before", "new_text", "after")).success());
        assertEquals("after", Files.readString(temp.resolve("one.txt")));
        ToolResult none = execute("edit_file", args("path", "one.txt", "old_text", "missing", "new_text", "x"));
        assertEquals("NOT_FOUND", none.errorCode());
        Files.writeString(temp.resolve("many.txt"), "same same");
        ToolResult many = execute("edit_file", args("path", "many.txt", "old_text", "same", "new_text", "x"));
        assertEquals("AMBIGUOUS", many.errorCode());
    }

    @Test void globAndSearchReturnRelativeLocations() throws Exception {
        Files.createDirectories(temp.resolve("src")); Files.writeString(temp.resolve("src/App.java"), "class App { // Needle\n}");
        ToolResult glob = execute("glob", args("pattern", "**/*.java"));
        assertTrue(glob.output().contains("src" + java.io.File.separator + "App.java"));
        ToolResult search = execute("search_text", args("query", "needle", "path", "src"));
        assertTrue(search.output().contains("App.java:1:"));
    }

    @Test void doubleStarGlobAlsoMatchesWorkspaceRoot() throws Exception {
        Files.writeString(temp.resolve("README.md"), "root");
        ToolResult result = execute("glob", args("pattern", "**/README*.md"));
        assertTrue(result.success()); assertTrue(result.output().contains("README.md"));
    }

    @Test void bashReturnsOutputAndNonZeroAsStructuredResult() {
        ToolResult ok = execute("bash", args("command", "Write-Output tool-ok"));
        assertTrue(ok.success(), ok.modelText()); assertTrue(ok.output().contains("tool-ok"));
        ToolResult failed = execute("bash", args("command", "Write-Error failed; exit 7"));
        assertFalse(failed.success()); assertEquals("NON_ZERO_EXIT", failed.errorCode()); assertTrue(failed.output().contains("exit_code: 7"));
    }

    @Test void rejectsLargeFileAndLimitsLongText() throws Exception {
        Files.write(temp.resolve("large.txt"), new byte[1024 * 1024 + 1]);
        ToolResult read = execute("read_file", args("path", "large.txt"));
        assertEquals("TOO_LARGE", read.errorCode());
        ToolContext.Limited limited = ToolContext.limit("x".repeat(ToolContext.MAX_RESULT_CHARS + 10));
        assertTrue(limited.truncated()); assertTrue(limited.text().endsWith("[truncated]"));
    }

    @Test void globAndSearchLimitLargeResultSets() throws Exception {
        Path many = Files.createDirectories(temp.resolve("many"));
        for (int i = 0; i < 205; i++) Files.writeString(many.resolve("F" + i + ".txt"), "needle");
        ToolResult glob = execute("glob", args("pattern", "many/*.txt"));
        ToolResult search = execute("search_text", args("query", "needle", "path", "many"));
        assertTrue(glob.truncated()); assertTrue(search.truncated());
    }

    @Test void bashTimeoutReturnsStructuredFailure() {
        var bash = new com.starcode.tool.builtin.BashTool(Duration.ofMillis(150));
        ToolCall call = new ToolCall("slow", "bash", args("command", "Start-Sleep -Seconds 3"));
        long started = System.nanoTime(); ToolResult result = bash.execute(call, context);
        assertEquals("TIMEOUT", result.errorCode());
        assertTrue(Duration.ofNanos(System.nanoTime() - started).toSeconds() < 2);
    }

    @Test void registryAppliesUniformPerToolTimeout() {
        Tool slow = new Tool() {
            public ToolDefinition definition() {
                return new ToolDefinition("slow", "slow", JSON.createObjectNode().put("type", "object"));
            }
            public Duration timeout() { return Duration.ofMillis(75); }
            public ToolResult execute(ToolCall call, ToolContext ignored) {
                try { Thread.sleep(30_000); }
                catch (InterruptedException error) { Thread.currentThread().interrupt(); }
                return ToolResult.success(call, "late", false);
            }
        };
        ToolRegistry local = new ToolRegistry().register(slow);
        ToolResult result = local.execute(new ToolCall("slow-call", "slow", JSON.createObjectNode()),
                context, new CancellationToken());
        assertEquals("TOOL_TIMEOUT", result.errorCode());
    }

    @Test void explicitCwdScopesAllCoreToolsWithoutChangingSchemas() throws Exception {
        Path worktree = Files.createDirectories(temp.resolve(".mewcode/worktrees/cwd-test"));
        Files.writeString(worktree.resolve("probe.txt"), "needle in worktree");
        ToolContext isolated = context.withCwd(worktree);

        ToolResult read = registry.execute(new ToolCall("r", "read_file", args("path", "probe.txt")), isolated);
        ToolResult write = registry.execute(new ToolCall("w", "write_file",
                args("path", "made.txt", "content", "before")), isolated);
        ToolResult edit = registry.execute(new ToolCall("e", "edit_file",
                args("path", "made.txt", "old_text", "before", "new_text", "after")), isolated);
        ToolResult glob = registry.execute(new ToolCall("g", "glob", args("pattern", "*.txt")), isolated);
        ToolResult search = registry.execute(new ToolCall("s", "search_text",
                args("query", "needle", "path", ".")), isolated);
        ToolResult bash = registry.execute(new ToolCall("b", "bash", args("command", "Get-Location")), isolated);

        assertTrue(read.success()); assertTrue(read.output().contains("needle in worktree"));
        assertTrue(write.success()); assertTrue(edit.success());
        assertEquals("after", Files.readString(worktree.resolve("made.txt")));
        assertTrue(glob.output().contains("probe.txt"));
        assertTrue(search.output().contains("probe.txt:1"));
        assertTrue(bash.output().contains(worktree.getFileName().toString()));
        assertFalse(Files.exists(temp.resolve("made.txt")));
        assertFalse(registry.execute(new ToolCall("x", "read_file", args("path", "../outside.txt")), isolated).success());
        assertTrue(registry.definitions().stream().noneMatch(definition -> definition.inputSchema().has("cwd")));
    }

    private ToolResult execute(String name, ObjectNode arguments) {
        return registry.execute(new ToolCall("call-1", name, arguments), context);
    }
    private ObjectNode args(String... values) {
        ObjectNode node = JSON.createObjectNode();
        for (int i = 0; i < values.length; i += 2) node.put(values[i], values[i + 1]);
        return node;
    }
}
