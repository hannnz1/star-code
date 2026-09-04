package com.starcode.team;

public final class MemberExistsException extends TeamException {
    public MemberExistsException(String name) {
        super("Team member already exists: " + name);
    }
}
