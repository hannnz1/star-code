package com.starcode.memory;

public record MemoryUpdateAction(String action, String level, String type, String title,
                                 String slug, String content, String filename) {}
