package com.starcode.team;

public final class MemberNotFoundException extends TeamException {
    public MemberNotFoundException(String name) {
        super("Team member not found: " + name);
    }
}
