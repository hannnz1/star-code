package com.starcode.ui;

import org.jline.reader.Parser;
import org.jline.reader.impl.DefaultParser;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WindowsPathInputTest {
    @Test void parserPreservesWindowsBackslashes() {
        DefaultParser parser = new DefaultParser().escapeChars(new char[0]);
        var parsed = parser.parse("请读取 tmp-agent-test\\hello.txt", 0, Parser.ParseContext.ACCEPT_LINE);
        assertEquals("tmp-agent-test\\hello.txt", parsed.words().get(1));
    }
}
