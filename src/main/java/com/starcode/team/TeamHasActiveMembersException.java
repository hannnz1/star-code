package com.starcode.team;

public final class TeamHasActiveMembersException extends TeamException {
    public TeamHasActiveMembersException(String name) {
        super("Team has active members: " + name);
    }
}
