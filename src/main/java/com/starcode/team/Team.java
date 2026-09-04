package com.starcode.team;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.locks.ReentrantLock;

public final class Team {
    private final ReentrantLock lock = new ReentrantLock();
    private final Path configDir;
    private final Path configPath;
    private final Path mailboxDir;
    private final Path tasksPath;
    private String name;
    private String description;
    private BackendType backend;
    private long createdAt;
    private List<TeammateInfo> members;

    Team(Path configDir, TeamSnapshot snapshot) {
        this.configDir = configDir.toAbsolutePath().normalize();
        this.configPath = this.configDir.resolve("config.json");
        this.mailboxDir = this.configDir.resolve("mailbox");
        this.tasksPath = this.configDir.resolve("tasks.json");
        apply(snapshot);
    }

    public String name() { return name; }
    public String description() { return description; }
    public BackendType backend() { return backend; }
    public long createdAt() { return createdAt; }
    public Path configDir() { return configDir; }
    public Path configPath() { return configPath; }
    public Path mailboxDir() { return mailboxDir; }
    public Path tasksPath() { return tasksPath; }

    public List<TeammateInfo> members() {
        lock.lock();
        try { refreshQuietly(); return members.stream().sorted(Comparator.comparing(TeammateInfo::name)).toList(); }
        finally { lock.unlock(); }
    }

    public Optional<TeammateInfo> memberByName(String memberName) {
        lock.lock();
        try { refreshQuietly(); return members.stream().filter(member -> member.name().equals(memberName)).findFirst(); }
        finally { lock.unlock(); }
    }

    public Optional<TeammateInfo> memberByAgentId(String agentId) {
        lock.lock();
        try { refreshQuietly(); return members.stream().filter(member -> member.agentId().equals(agentId)).findFirst(); }
        finally { lock.unlock(); }
    }

    public boolean addMember(TeammateInfo member) throws IOException {
        lock.lock();
        try {
            reload();
            if (members.stream().anyMatch(existing -> existing.name().equals(member.name())))
                throw new MemberExistsException(member.name());
            members.add(member);
            save();
            return true;
        } finally { lock.unlock(); }
    }

    public boolean setMemberActive(String memberName, boolean active) throws IOException {
        lock.lock();
        try {
            reload();
            for (int index = 0; index < members.size(); index++) {
                TeammateInfo member = members.get(index);
                if (member.name().equals(memberName)) {
                    members.set(index, member.withActive(active));
                    save();
                    return true;
                }
            }
            throw new MemberNotFoundException(memberName);
        } finally { lock.unlock(); }
    }

    public boolean removeMember(String memberName) throws IOException {
        if ("lead".equals(memberName)) throw new TeamException("The lead member cannot be removed");
        lock.lock();
        try {
            reload();
            boolean removed = members.removeIf(member -> member.name().equals(memberName));
            if (!removed) throw new MemberNotFoundException(memberName);
            save();
            return true;
        } finally { lock.unlock(); }
    }

    TeamSnapshot snapshot() {
        lock.lock();
        try { return new TeamSnapshot(name, description, backend, createdAt, List.copyOf(members)); }
        finally { lock.unlock(); }
    }

    private void reload() throws IOException {
        Optional<TeamSnapshot> disk = Persistence.readJson(configPath, TeamSnapshot.class);
        disk.ifPresent(this::apply);
    }

    private void refreshQuietly() {
        try { reload(); }
        catch (IOException error) { System.err.println("Team refresh skipped: " + error.getMessage()); }
    }

    private void apply(TeamSnapshot snapshot) {
        name = snapshot.name();
        description = snapshot.description() == null ? "" : snapshot.description();
        backend = snapshot.backend() == null ? BackendType.IN_PROCESS : snapshot.backend();
        createdAt = snapshot.createdAt();
        members = new ArrayList<>(snapshot.members());
    }

    private void save() throws IOException {
        Persistence.atomicWriteJson(configPath,
                new TeamSnapshot(name, description, backend, createdAt, List.copyOf(members)));
    }
}
