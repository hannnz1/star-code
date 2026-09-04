package com.starcode.permission;

import java.util.Objects;

public record NotValueMatcher(ValueMatcher inner) implements ValueMatcher {
    public NotValueMatcher {
        Objects.requireNonNull(inner, "inner");
    }

    @Override
    public boolean matches(String value, boolean pathValue) {
        return !inner.matches(value, pathValue);
    }

    @Override
    public String describe() {
        return "!" + inner.describe();
    }
}
