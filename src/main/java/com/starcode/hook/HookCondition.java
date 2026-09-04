package com.starcode.hook;

import com.starcode.permission.ValueMatcher;
import java.util.List;
import java.util.Objects;

public record HookCondition(Mode mode, List<Atom> atoms) {
    public enum Mode { ALL, ANY }

    public record Atom(String field, ValueMatcher matcher) {
        public Atom {
            field = Objects.requireNonNullElse(field, "");
            Objects.requireNonNull(matcher, "matcher");
        }

        boolean matches(HookPayload payload) {
            return matcher.matches(payload.field(field), true);
        }
    }

    public HookCondition {
        Objects.requireNonNull(mode, "mode");
        atoms = List.copyOf(atoms);
    }

    public boolean matches(HookPayload payload) {
        if (atoms.isEmpty()) return mode == Mode.ALL;
        return mode == Mode.ALL
                ? atoms.stream().allMatch(atom -> atom.matches(payload))
                : atoms.stream().anyMatch(atom -> atom.matches(payload));
    }
}
