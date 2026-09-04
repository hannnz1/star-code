package com.starcode.permission;

/** Shared value matching contract used by permission rules and lifecycle hooks. */
public sealed interface ValueMatcher
        permits ExactValueMatcher, GlobValueMatcher, RegexValueMatcher, NotValueMatcher {
    boolean matches(String value, boolean pathValue);

    String describe();
}
