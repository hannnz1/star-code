package com.starcode.team;

public final class TeamNotFoundException extends TeamException {
    public TeamNotFoundException(String name) {
        super("Team not found: " + name);
    }
}
