package com.starcode.llm;

public sealed interface StreamEvent permits StreamEvent.TextDelta, StreamEvent.Completed {
    record TextDelta(String text) implements StreamEvent {}
    record Completed() implements StreamEvent {}
}

