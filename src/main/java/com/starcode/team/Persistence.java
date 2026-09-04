package com.starcode.team;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Optional;
import java.util.regex.Pattern;

public final class Persistence {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Pattern UNSAFE = Pattern.compile("[^A-Za-z0-9._-]+");

    private Persistence() {}

    public static String sanitize(String value) {
        if (value == null) return "";
        return UNSAFE.matcher(value.strip()).replaceAll("-").replaceAll("^-+|-+$", "");
    }

    public static void atomicWriteJson(Path path, Object value) throws IOException {
        Files.createDirectories(path.toAbsolutePath().normalize().getParent());
        Path temp = path.resolveSibling(path.getFileName() + ".tmp");
        byte[] bytes = JSON.writerWithDefaultPrettyPrinter().writeValueAsBytes(value);
        Files.write(temp, bytes, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
        try {
            Files.move(temp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException error) {
            Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    public static <T> Optional<T> readJson(Path path, Class<T> type) throws IOException {
        if (!Files.isRegularFile(path)) return Optional.empty();
        return Optional.of(JSON.readValue(Files.readAllBytes(path), type));
    }
}
