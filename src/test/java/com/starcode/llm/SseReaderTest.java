package com.starcode.llm;

import org.junit.jupiter.api.Test;
import java.io.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class SseReaderTest {
    @Test void joinsDataLinesAndEmitsEvents() throws Exception {
        String source = "event: x\ndata: {\\\"a\\\":1}\n\ndata: first\ndata: second\n\n";
        List<String> values = new ArrayList<>();
        SseReader.read(new BufferedReader(new StringReader(source)), values::add);
        assertEquals(List.of("{\\\"a\\\":1}", "first\nsecond"), values);
    }
}

