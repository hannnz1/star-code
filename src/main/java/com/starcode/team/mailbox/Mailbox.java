package com.starcode.team.mailbox;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.team.Persistence;
import com.starcode.team.filelock.FileLock;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class Mailbox {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final TypeReference<List<Message>> MESSAGES = new TypeReference<>() {};
    private final Path dir;

    public Mailbox(Path dir) throws IOException {
        this.dir = dir.toAbsolutePath().normalize();
        Files.createDirectories(this.dir);
    }

    public void write(String agentId, Message message) throws IOException {
        validateId(agentId);
        Path file = file(agentId);
        try (FileLock.Lease ignored = FileLock.acquire(lock(agentId))) {
            List<Message> values = new ArrayList<>(readUnlocked(file));
            values.add(message.normalized());
            Persistence.atomicWriteJson(file, values);
        }
    }

    public List<Message> read(String agentId) throws IOException {
        validateId(agentId);
        try (FileLock.Lease ignored = FileLock.acquire(lock(agentId))) {
            return List.copyOf(readUnlocked(file(agentId)));
        }
    }

    public ReadUnreadResult readUnread(String agentId) throws IOException {
        List<Message> values = read(agentId);
        List<Integer> indices = new ArrayList<>();
        List<Message> unread = new ArrayList<>();
        for (int index = 0; index < values.size(); index++) {
            if (!values.get(index).read()) { indices.add(index); unread.add(values.get(index)); }
        }
        return new ReadUnreadResult(indices, unread);
    }

    public void markRead(String agentId, List<Integer> indices) throws IOException {
        validateId(agentId);
        Set<Integer> selected = new HashSet<>(indices);
        Path file = file(agentId);
        try (FileLock.Lease ignored = FileLock.acquire(lock(agentId))) {
            List<Message> values = new ArrayList<>(readUnlocked(file));
            for (int index = 0; index < values.size(); index++) {
                if (selected.contains(index)) values.set(index, values.get(index).asRead());
            }
            Persistence.atomicWriteJson(file, values);
        }
    }

    private List<Message> readUnlocked(Path file) throws IOException {
        if (!Files.isRegularFile(file)) return List.of();
        return JSON.readValue(Files.readAllBytes(file), MESSAGES);
    }

    private Path file(String agentId) { return dir.resolve(agentId + ".json"); }
    private Path lock(String agentId) { return dir.resolve(agentId + ".lock"); }

    private static void validateId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9._-]+"))
            throw new IllegalArgumentException("Invalid mailbox agent id: " + value);
    }
}
