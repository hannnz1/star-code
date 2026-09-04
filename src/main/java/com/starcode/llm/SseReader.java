package com.starcode.llm;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.function.Consumer;

public final class SseReader {
    private SseReader() {}
    public static void read(BufferedReader reader, Consumer<String> dataConsumer) throws IOException {
        StringBuilder data = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            if (line.isEmpty()) {
                if (!data.isEmpty()) {
                    dataConsumer.accept(data.toString());
                    data.setLength(0);
                }
            } else if (line.startsWith("data:")) {
                if (!data.isEmpty()) data.append('\n');
                data.append(line.substring(5).stripLeading());
            }
        }
        if (!data.isEmpty()) dataConsumer.accept(data.toString());
    }
}

