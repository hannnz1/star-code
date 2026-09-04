package com.starcode.team.filelock;

import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class FileLock {
    static final int MAX_RETRIES = 10;
    static final Duration STALE_AFTER = Duration.ofSeconds(10);

    private FileLock() {}

    public static Lease acquire(Path path) throws IOException {
        Files.createDirectories(path.toAbsolutePath().normalize().getParent());
        IOException failure = null;
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE).close();
                return new Lease(path);
            } catch (FileAlreadyExistsException exists) {
                failure = exists;
                if (isStale(path)) {
                    Files.deleteIfExists(path);
                    continue;
                }
                try {
                    Thread.sleep(ThreadLocalRandom.current().nextLong(5, 101));
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Interrupted while waiting for file lock: " + path, interrupted);
                }
            }
        }
        throw new IOException("Could not acquire file lock after " + MAX_RETRIES + " attempts: " + path, failure);
    }

    private static boolean isStale(Path path) {
        try { return Files.getLastModifiedTime(path).toInstant().isBefore(Instant.now().minus(STALE_AFTER)); }
        catch (IOException error) { return false; }
    }

    public static final class Lease implements AutoCloseable {
        private final Path path;
        private boolean closed;

        Lease(Path path) { this.path = path; }

        @Override public void close() throws IOException {
            if (!closed) { closed = true; Files.deleteIfExists(path); }
        }
    }
}
