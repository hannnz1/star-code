package com.starcode.memory;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.llm.*;
import com.starcode.prompt.PromptContext;
import com.starcode.tool.*;
import java.nio.file.*;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MemoryManagerTest {
    @TempDir Path temp;

    @Test void explicitMemoryRequestUpdatesIndexAsynchronously() throws Exception {
        AtomicInteger calls = new AtomicInteger();
        LlmClient fake = new LlmClient() {
            @Override public Completion stream(List<ChatMessage> history, String userText,
                                               List<ToolDefinition> tools, Consumer<StreamEvent> events) {
                calls.incrementAndGet();
                assertTrue(tools.isEmpty());
                return new Completion("""
                        [{"action":"create","level":"user","type":"user_preference",
                        "title":"Concise replies","slug":"concise_replies","content":"Prefer concise replies."}]
                        """);
            }
            @Override public Completion continueWithTools(List<ChatMessage> history, String userText,
                    List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
                throw new AssertionError("Memory update must not use tools");
            }
        };
        PromptContext prompt = new PromptContext();
        Path project = temp.resolve("project-memory"), user = temp.resolve("user-memory");
        try (MemoryManager manager = new MemoryManager(project, user, fake, prompt)) {
            manager.afterCompletedTurn("请记住我喜欢简洁回复", "好的");
            long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(3);
            while ((manager.updating() || calls.get() == 0) && System.nanoTime() < deadline) Thread.sleep(10);
            assertEquals(1, calls.get());
            assertTrue(Files.isRegularFile(user.resolve("user_preference_concise_replies.md")));
            assertTrue(prompt.memory().contains("Concise replies"));
        }
    }

    @Test void suppressionSignalSkipsUpdate() {
        AtomicInteger calls = new AtomicInteger();
        LlmClient unused = new LlmClient() {
            @Override public Completion stream(List<ChatMessage> history, String userText,
                    List<ToolDefinition> tools, Consumer<StreamEvent> events) {
                calls.incrementAndGet(); return new Completion("[]");
            }
            @Override public Completion continueWithTools(List<ChatMessage> history, String userText,
                    List<ToolExchange> exchanges, List<ToolDefinition> tools, Consumer<StreamEvent> events) {
                return new Completion("[]");
            }
        };
        try (MemoryManager manager = new MemoryManager(temp.resolve("p"), temp.resolve("u"), unused,
                new PromptContext())) {
            manager.afterCompletedTurn("不要记住这条消息", "好的");
        }
        assertEquals(0, calls.get());
    }

    @Test void listFilesIncludesMarkdownIndexesAndSortsEachLevel() throws Exception {
        Path project = Files.createDirectories(temp.resolve("p"));
        Path user = Files.createDirectories(temp.resolve("u"));
        Files.writeString(project.resolve("project_knowledge_z.md"), "z");
        Files.writeString(project.resolve("MEMORY.md"), "index");
        Files.writeString(project.resolve("ignored.txt"), "ignored");
        Files.writeString(user.resolve("user_preference_a.md"), "a");
        try (MemoryManager manager = new MemoryManager(project, user, null, new PromptContext())) {
            MemoryManager.Files files = manager.listFiles();
            assertEquals(List.of("MEMORY.md", "project_knowledge_z.md"), files.project());
            assertEquals(List.of("user_preference_a.md"), files.user());
        }
    }
}
