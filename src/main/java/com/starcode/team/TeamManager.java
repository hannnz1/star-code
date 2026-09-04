package com.starcode.team;

import com.starcode.task.SubAgentTaskManager;
import com.starcode.permission.PermissionMode;
import com.starcode.team.backend.BackendDetector;
import com.starcode.team.backend.BackendFactory;
import com.starcode.team.mailbox.Mailbox;
import com.starcode.team.mailbox.Message;
import com.starcode.team.mailbox.MessageType;
import com.starcode.team.registry.AgentNameRegistry;
import com.starcode.team.tasks.TeamTaskStore;
import com.starcode.worktree.ExitOptions;
import com.starcode.worktree.Worktree;
import com.starcode.worktree.WorktreeManager;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.locks.ReentrantLock;
import java.util.stream.Stream;

public final class TeamManager {
    private final ReentrantLock lock = new ReentrantLock();
    private final Map<String, Team> teams = new LinkedHashMap<>();
    private final Path projectRoot;
    private final Path teamsRoot;
    private final WorktreeManager worktrees;
    private final SubAgentTaskManager backgroundTasks;
    private final AgentNameRegistry names;

    public TeamManager(Path homeDir, Path projectRoot, WorktreeManager worktrees,
                       SubAgentTaskManager backgroundTasks, AgentNameRegistry names) throws IOException {
        this.projectRoot = projectRoot.toAbsolutePath().normalize();
        this.teamsRoot = homeDir.toAbsolutePath().normalize().resolve(".mewcode").resolve("teams");
        this.worktrees = worktrees;
        this.backgroundTasks = backgroundTasks;
        this.names = names == null ? new AgentNameRegistry() : names;
        Files.createDirectories(teamsRoot);
        load();
        if (backgroundTasks != null) backgroundTasks.onTaskDone(this::handleTaskDone);
    }

    public Path teamsRoot() { return teamsRoot; }
    public Path projectRoot() { return projectRoot; }

    public Team create(String requestedName, String description) throws IOException {
        String base = Persistence.sanitize(requestedName);
        if (base.isBlank()) throw new IllegalArgumentException("Team name is empty after sanitization");
        lock.lock();
        try {
            String name = base;
            for (int suffix = 2; teams.containsKey(name) || Files.exists(teamsRoot.resolve(name)); suffix++)
                name = base + "-" + suffix;
            Path directory = teamsRoot.resolve(name).normalize();
            ensureManaged(directory);
            Files.createDirectories(directory.resolve("mailbox"));
            BackendType backend = BackendDetector.detect();
            TeammateInfo lead = new TeammateInfo("lead", "lead", "lead", "inherit", backend,
                    "", "", "", true);
            TeamSnapshot snapshot = new TeamSnapshot(name, description == null ? "" : description.strip(),
                    backend, Instant.now().getEpochSecond(), List.of(lead));
            try {
                Persistence.atomicWriteJson(directory.resolve("config.json"), snapshot);
            } catch (IOException error) {
                deleteTree(directory);
                throw error;
            }
            Team team = new Team(directory, snapshot);
            teams.put(name, team);
            names.register("lead", "lead");
            return team;
        } finally { lock.unlock(); }
    }

    public Optional<Team> get(String name) {
        lock.lock();
        try {
            Team exact = teams.get(name);
            if (exact != null) return Optional.of(exact);
            return Optional.ofNullable(teams.get(Persistence.sanitize(name)));
        } finally { lock.unlock(); }
    }

    public Team require(String name) {
        return get(name).orElseThrow(() -> new TeamNotFoundException(name));
    }

    public List<Team> list() {
        lock.lock();
        try { return teams.values().stream().sorted(Comparator.comparingLong(Team::createdAt)).toList(); }
        finally { lock.unlock(); }
    }

    public TeamTaskStore tasks(String teamName) { return new TeamTaskStore(require(teamName).tasksPath()); }

    public Mailbox mailbox(String teamName) throws IOException { return new Mailbox(require(teamName).mailboxDir()); }

    public void addMember(String teamName, TeammateInfo member) throws IOException {
        Team team = require(teamName);
        team.addMember(member);
        names.register(member.name(), member.agentId());
        if (backgroundTasks != null) {
            backgroundTasks.get(member.agentId()).ifPresent(task -> {
                if (task.status() != com.starcode.task.TaskStatus.RUNNING) handleTaskDone(member.agentId());
            });
        }
    }

    public List<String> sendMessage(String teamName, String to, Message message) throws IOException {
        Team team = require(teamName);
        List<TeammateInfo> targets;
        if ("*".equals(to)) {
            targets = team.members().stream().filter(member -> !member.agentId().equals(message.from())).toList();
        } else {
            TeammateInfo member = team.memberByName(to).or(() -> team.memberByAgentId(to))
                    .orElseThrow(() -> new MemberNotFoundException(to));
            targets = List.of(member);
        }
        Mailbox mailbox = new Mailbox(team.mailboxDir());
        List<String> delivered = new ArrayList<>();
        for (TeammateInfo target : targets) {
            mailbox.write(target.agentId(), message);
            delivered.add(target.agentId());
            if (target.backendType() == BackendType.IN_PROCESS) resumeInProcessIfIdle(team, target, message);
            else wakePane(target);
        }
        return List.copyOf(delivered);
    }

    public void delete(String name, boolean force) throws IOException {
        lock.lock();
        try {
            Team team = teams.get(Persistence.sanitize(name));
            if (team == null) throw new TeamNotFoundException(name);
            boolean active = team.members().stream().anyMatch(member -> !"lead".equals(member.name()) && member.active());
            if (active && !force) throw new TeamHasActiveMembersException(team.name());
            if (force) killPanes(team);
            cleanupWorktrees(team, force);
            for (TeammateInfo member : team.members()) names.unregisterByAgentId(member.agentId());
            deleteTree(team.configDir());
            teams.remove(team.name());
        } finally { lock.unlock(); }
    }

    public List<LeadMessage> pollLeadMailboxes() {
        List<LeadMessage> result = new ArrayList<>();
        for (Team team : list()) {
            try {
                Mailbox mailbox = new Mailbox(team.mailboxDir());
                var unread = mailbox.readUnread("lead");
                for (Message message : unread.messages())
                    result.add(new LeadMessage(team.name(), message.from(), message.type(), message.text(),
                            message.timestamp()));
                if (!unread.indices().isEmpty()) mailbox.markRead("lead", unread.indices());
            } catch (Exception error) {
                System.err.println("Lead mailbox poll skipped for " + team.name() + ": " + safe(error));
            }
        }
        return List.copyOf(result);
    }

    public void handleTaskDone(String agentId) {
        Optional<String> memberName = names.nameOf(agentId);
        if (memberName.isEmpty()) return;
        for (Team team : list()) {
            Optional<TeammateInfo> member = team.memberByAgentId(agentId);
            if (member.isEmpty()) continue;
            try {
                team.setMemberActive(member.get().name(), false);
                Message completion = backgroundTasks == null ? null : backgroundTasks.get(agentId)
                        .map(task -> task.permissionMode() == PermissionMode.PLAN
                                && task.status() == com.starcode.task.TaskStatus.COMPLETED
                                ? new Message(member.get().name(), task.result(), "", false, null,
                                        MessageType.PLAN_APPROVAL_REQUEST, "plan_" + agentId, null)
                                : null).orElse(null);
                if (completion == null) completion = new Message(member.get().name(),
                        "[idle] " + member.get().name() + " (reason: available)", "", false,
                        null, MessageType.TEXT, null, null);
                new Mailbox(team.mailboxDir()).write("lead", completion);
            } catch (Exception error) {
                System.err.println("Team completion notification failed: " + safe(error));
            }
            return;
        }
    }

    private void load() throws IOException {
        try (Stream<Path> directories = Files.list(teamsRoot)) {
            for (Path directory : directories.filter(path -> Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                    && !Files.isSymbolicLink(path)).toList()) {
                try {
                    Optional<TeamSnapshot> snapshot = Persistence.readJson(directory.resolve("config.json"), TeamSnapshot.class);
                    if (snapshot.isEmpty()) continue;
                    Team team = new Team(directory, snapshot.get());
                    teams.put(team.name(), team);
                    for (TeammateInfo member : team.members()) names.register(member.name(), member.agentId());
                } catch (Exception error) {
                    System.err.println("Team config skipped: " + directory + ": " + safe(error));
                }
            }
        }
    }

    private void cleanupWorktrees(Team team, boolean force) {
        if (worktrees == null) return;
        Map<Path, Worktree> managed = new LinkedHashMap<>();
        for (Worktree worktree : worktrees.list())
            managed.put(worktree.path().toAbsolutePath().normalize(), worktree);
        for (TeammateInfo member : team.members()) {
            if (member.worktreePath() == null || member.worktreePath().isBlank()) continue;
            Worktree worktree = managed.get(Path.of(member.worktreePath()).toAbsolutePath().normalize());
            if (worktree == null) continue;
            try { worktrees.remove(worktree.name(), force ? ExitOptions.discard() : ExitOptions.protectChanges()); }
            catch (Exception error) { System.err.println("Team worktree cleanup skipped: " + safe(error)); }
        }
    }

    private void wakePane(TeammateInfo member) {
        if (member.paneId() == null || member.paneId().isBlank()) return;
        try { BackendFactory.create(member.backendType()).wake(member.paneId(), member.agentId()); }
        catch (Exception error) { System.err.println("Team pane wake failed: " + safe(error)); }
    }

    private void killPanes(Team team) {
        for (TeammateInfo member : team.members()) {
            if (member.backendType() == BackendType.IN_PROCESS) {
                if (backgroundTasks != null) backgroundTasks.stop(member.agentId());
                continue;
            }
            if (member.paneId() == null || member.paneId().isBlank()) continue;
            try { BackendFactory.create(member.backendType()).kill(member.paneId(), member.agentId()); }
            catch (Exception error) { System.err.println("Team pane cleanup skipped: " + safe(error)); }
        }
    }

    private void resumeInProcessIfIdle(Team team, TeammateInfo target, Message message) {
        if (backgroundTasks == null || target.backendType() != BackendType.IN_PROCESS) return;
        try {
            if (message.type() == MessageType.SHUTDOWN_REQUEST) {
                backgroundTasks.stop(target.agentId());
                team.setMemberActive(target.name(), false);
                new Mailbox(team.mailboxDir()).write("lead", new Message(target.name(),
                        "shutdown complete", "", false, null, MessageType.SHUTDOWN_RESPONSE,
                        message.requestId(), true));
                return;
            }
            if (message.type() == MessageType.PLAN_APPROVAL_RESPONSE) {
                if (!Boolean.TRUE.equals(message.approve())) return;
                backgroundTasks.permissionMode(target.name(), PermissionMode.DEFAULT);
            }
            String reminder = "<incoming-messages>\nFrom " + message.from() + ": "
                    + message.text() + "\n</incoming-messages>";
            if (backgroundTasks.notifyRunning(target.name(), reminder)) return;
            backgroundTasks.sendMessage(target.name(), reminder);
            team.setMemberActive(target.name(), true);
        } catch (IllegalArgumentException | IllegalStateException ignored) {
            // A running worker consumes the mailbox on its next iteration.
        } catch (IOException error) {
            System.err.println("Team member state update failed: " + safe(error));
        }
    }

    private void ensureManaged(Path directory) throws IOException {
        if (!directory.startsWith(teamsRoot) || directory.equals(teamsRoot))
            throw new IOException("Team directory is outside the managed root");
    }

    private void deleteTree(Path directory) throws IOException {
        Path normalized = directory.toAbsolutePath().normalize();
        ensureManaged(normalized);
        if (!Files.exists(normalized)) return;
        try (Stream<Path> walk = Files.walk(normalized)) {
            for (Path path : walk.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
        }
    }

    private static String safe(Throwable error) {
        return error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
    }

    public record LeadMessage(String teamName, String from, MessageType type, String text, String timestamp) {}
}
