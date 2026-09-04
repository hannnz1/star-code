package com.starcode.session;

import java.io.IOException;
import java.nio.file.*;
import java.time.*;
import java.util.Comparator;
import java.util.stream.Stream;

public final class SessionCleaner {
    private SessionCleaner() {}
    public static void cleanExpired(Path sessionsDir, Duration age, String currentId) {
        if (!Files.isDirectory(sessionsDir)) return;
        try (Stream<Path> paths = Files.list(sessionsDir)) {
            paths.forEach(dir -> {
                String id = dir.getFileName().toString(); if (id.equals(currentId) || Files.isSymbolicLink(dir)) return;
                try {
                    Instant created = SessionContext.parseSessionTime(id).atZone(ZoneId.systemDefault()).toInstant();
                    if (Duration.between(created, Instant.now()).compareTo(age) > 0) deleteTree(dir, sessionsDir);
                } catch (Exception ignored) { }
            });
        } catch (IOException ignored) { }
    }
    private static void deleteTree(Path dir, Path root) throws IOException {
        Path normalized = dir.toAbsolutePath().normalize(), boundary = root.toAbsolutePath().normalize();
        if (!normalized.startsWith(boundary) || normalized.equals(boundary)) throw new IOException("Unsafe delete path");
        try (Stream<Path> paths = Files.walk(dir)) {
            for (Path path : paths.sorted(Comparator.reverseOrder()).toList())
                if (!Files.isSymbolicLink(path)) Files.deleteIfExists(path); else Files.deleteIfExists(path);
        }
    }
}
