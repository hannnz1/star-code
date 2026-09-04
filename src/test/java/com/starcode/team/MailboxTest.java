package com.starcode.team;

import static org.junit.jupiter.api.Assertions.*;

import com.starcode.team.filelock.FileLock;
import com.starcode.team.mailbox.Mailbox;
import com.starcode.team.mailbox.Message;
import com.starcode.team.mailbox.MessageType;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MailboxTest {
    @TempDir Path temp;

    @Test void writesReadsAndMarksUnreadMessages() throws Exception {
        Mailbox mailbox = new Mailbox(temp.resolve("mailbox"));
        mailbox.write("agent-1", message("one"));
        mailbox.write("agent-1", message("two"));
        var unread = mailbox.readUnread("agent-1");
        assertEquals(List.of(0, 1), unread.indices());
        mailbox.markRead("agent-1", List.of(0));
        assertTrue(mailbox.read("agent-1").get(0).read());
        assertFalse(mailbox.read("agent-1").get(1).read());
    }

    @Test void concurrentWritersDoNotLoseMessages() throws Exception {
        Mailbox mailbox = new Mailbox(temp.resolve("concurrent"));
        List<CompletableFuture<Void>> futures = new ArrayList<>();
        for (int index = 0; index < 10; index++) {
            int value = index;
            futures.add(CompletableFuture.runAsync(() -> {
                try { mailbox.write("agent", message("m" + value)); }
                catch (Exception error) { throw new RuntimeException(error); }
            }, command -> Thread.startVirtualThread(command)));
        }
        CompletableFuture.allOf(futures.toArray(CompletableFuture[]::new)).join();
        assertEquals(10, mailbox.read("agent").size());
    }

    @Test void staleLockCanBeReclaimed() throws Exception {
        Path lock = temp.resolve("stale.lock");
        Files.writeString(lock, "");
        Files.setLastModifiedTime(lock, FileTime.from(Instant.now().minusSeconds(11)));
        try (FileLock.Lease ignored = FileLock.acquire(lock)) { assertTrue(Files.exists(lock)); }
        assertFalse(Files.exists(lock));
    }

    private static Message message(String text) {
        return new Message("lead", text, "", false, null, MessageType.TEXT, null, null);
    }
}
