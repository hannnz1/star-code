package com.starcode.permission;

import java.util.Objects;

public record ExactValueMatcher(String expected) implements ValueMatcher {
    public ExactValueMatcher {
        expected = Objects.requireNonNullElse(expected, "");
    }

    @Override
    public boolean matches(String value, boolean pathValue) {
        return expected.equals(Objects.requireNonNullElse(value, ""));
    }

    @Override
    public String describe() {
        return "=" + expected;
    }
}
