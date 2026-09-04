package com.starcode.team;

public final class InProcessTeammateNoSpawnException extends TeamException {
    public InProcessTeammateNoSpawnException() {
        super("In-process teammates cannot spawn nested team members");
    }
}
