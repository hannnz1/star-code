package com.starcode.permission;

import java.util.Objects;
import java.util.regex.Pattern;

public final class GlobValueMatcher implements ValueMatcher {
    private final String glob;
    private final Pattern textPattern;
    private final Pattern pathPattern;

    public GlobValueMatcher(String glob) {
        this.glob = Objects.requireNonNullElse(glob, "");
        this.textPattern = Pattern.compile(toRegex(this.glob, false));
        this.pathPattern = Pattern.compile(toRegex(this.glob, true));
    }

    @Override
    public boolean matches(String value, boolean pathValue) {
        return (pathValue ? pathPattern : textPattern)
                .matcher(Objects.requireNonNullElse(value, ""))
                .matches();
    }

    @Override
    public String describe() {
        return glob;
    }

    static String toRegex(String glob, boolean pathTarget) {
        StringBuilder regex = new StringBuilder("^");
        for (int i = 0; i < glob.length(); i++) {
            char current = glob.charAt(i);
            if (current == '*') {
                boolean doubled = i + 1 < glob.length() && glob.charAt(i + 1) == '*';
                if (doubled) i++;
                regex.append(pathTarget && !doubled ? "[^/\\\\]*" : ".*");
            } else if ("\\.[]{}()+-^$|?".indexOf(current) >= 0) {
                regex.append('\\').append(current);
            } else if (current == '\\' || current == '/') {
                regex.append("[/\\\\]");
            } else {
                regex.append(current);
            }
        }
        return regex.append('$').toString();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof GlobValueMatcher matcher && glob.equals(matcher.glob);
    }

    @Override
    public int hashCode() {
        return glob.hashCode();
    }
}
