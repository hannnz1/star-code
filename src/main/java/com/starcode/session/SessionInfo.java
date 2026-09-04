package com.starcode.session;

import java.nio.file.Path;
import java.time.Instant;

public record SessionInfo(String id, String title, Instant modifiedAt, String model, long size, Path dir) {}
