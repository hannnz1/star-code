package com.starcode.permission;

import java.util.Objects;
import java.util.regex.Pattern;

public final class RegexValueMatcher implements ValueMatcher {
    private final String expression;
    private final Pattern compiled;

    public RegexValueMatcher(String expression) {
        this.expression = Objects.requireNonNullElse(expression, "");
        this.compiled = Pattern.compile(this.expression);
    }

    @Override
    public boolean matches(String value, boolean pathValue) {
        return compiled.matcher(Objects.requireNonNullElse(value, "")).matches();
    }

    @Override
    public String describe() {
        return "~" + expression;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof RegexValueMatcher matcher && expression.equals(matcher.expression);
    }

    @Override
    public int hashCode() {
        return expression.hashCode();
    }
}
