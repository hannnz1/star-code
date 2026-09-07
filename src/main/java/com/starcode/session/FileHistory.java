package com.starcode.session;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.starcode.llm.ChatMessage;
import com.starcode.tool.ToolContext;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/** Durable checkpoints for dedicated file tools. Shell and external edits are not recorded. */
public final class FileHistory {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final long MAX_FILE_BYTES = 16 * 1024 * 1024;
    public record Change(String path, byte[] before, byte[] after) {}
    public record Checkpoint(int id, String label, List<ChatMessage> messages, List<Change> changes) {}
    public record State(int nextId, List<Checkpoint> checkpoints) {}
    public record RewindResult(List<ChatMessage> messages, List<String> paths) {}
    private final Path workspace, journal;
    private final List<Checkpoint> checkpoints = new ArrayList<>();
    private int nextId = 1;

    public FileHistory(Path workspace, Path sessionDir) throws IOException {
        this.workspace = workspace.toRealPath();
        this.journal = sessionDir.resolve("file-history.json");
        if (Files.exists(journal, LinkOption.NOFOLLOW_LINKS)) {
            if (Files.isSymbolicLink(journal)) throw new IOException("File-history journal is a symbolic link");
            State state = JSON.readValue(Files.readAllBytes(journal), State.class);
            checkpoints.addAll(state.checkpoints());
            for (Checkpoint point : checkpoints) {
                if (point.id() < nextId || point.messages() == null || point.changes() == null) throw new IOException("Invalid checkpoint journal");
                nextId = point.id() + 1;
                for (Change change : point.changes()) resolve(change.path());
            }
            if(state.nextId()<nextId) throw new IOException("Invalid checkpoint sequence");
            nextId=state.nextId();
        }
    }
    public synchronized int begin(String label, List<ChatMessage> messages) throws IOException {
        var point = new Checkpoint(nextId, label.length() > 120 ? label.substring(0,120) : label,
                List.copyOf(messages), new ArrayList<>());
        checkpoints.add(point);
        nextId++;
        try { persist(); } catch (IOException failure) { checkpoints.removeLast(); nextId--; throw failure; }
        return point.id();
    }
    public synchronized List<Checkpoint> checkpoints() {
        return checkpoints.stream().map(p -> new Checkpoint(p.id(), p.label(), p.messages(), List.copyOf(p.changes()))).toList();
    }
    public synchronized void write(Path path, byte[] content) throws IOException {
        String relative = workspace.relativize(path.toAbsolutePath().normalize()).toString();
        Path target = resolve(relative);
        if (content.length > MAX_FILE_BYTES) throw new IOException("Checkpoint file exceeds16MiB");
        if (checkpoints.isEmpty()) begin("File tool checkpoint", List.of());
        byte[] before = read(target);
        if (Arrays.equals(before, content)) return;
        var changes = checkpoints.getLast().changes();
        changes.add(new Change(relative, before, content.clone()));
        try { persist(); } catch (IOException failure) { changes.removeLast(); throw failure; }
        // Intent is durable before mutation; rewind accepts either side if execution was interrupted.
        atomicWrite(target, content);
    }
    public synchronized RewindResult rewind(int id, boolean files) throws IOException {
        int index = -1;
        for (int i=0;i<checkpoints.size();i++) if(checkpoints.get(i).id()==id) index=i;
        if(index<0) throw new IOException("Unknown checkpoint: " + id);
        List<ChatMessage> messages = checkpoints.get(index).messages();
        if(!files) return new RewindResult(messages, List.of());
        Map<Path, byte[]> current = new LinkedHashMap<>(), restored = new LinkedHashMap<>();
        for(int i=checkpoints.size()-1;i>=index;i--) {
            var changes = checkpoints.get(i).changes();
            for(int j=changes.size()-1;j>=0;j--) {
                var change = changes.get(j); Path target=resolve(change.path());
                if(!current.containsKey(target)) { byte[] value=read(target); current.put(target,value); restored.put(target,value); }
                byte[] value=restored.get(target);
                if(!Arrays.equals(value,change.after()) && !Arrays.equals(value,change.before()))
                    throw new IOException("File changed outside recorded tools; rewind refused: " + change.path());
                restored.put(target,change.before());
            }
        }
        List<Path> applied = new ArrayList<>();
        try {
            for(var item:restored.entrySet()) { restore(item.getKey(),item.getValue()); applied.add(item.getKey()); }
        } catch(IOException failure) {
            for(int i=applied.size()-1;i>=0;i--) try { restore(applied.get(i),current.get(applied.get(i))); }
            catch(IOException rollback) { failure.addSuppressed(rollback); }
            throw failure;
        }
        var previous = new ArrayList<>(checkpoints);
        // Keep the selected conversation checkpoint available if conversation persistence fails later.
        Checkpoint selected=checkpoints.get(index);
        checkpoints.subList(index, checkpoints.size()).clear();
        checkpoints.add(new Checkpoint(selected.id(), selected.label(), selected.messages(), new ArrayList<>()));
        try { persist(); }
        catch(IOException failure) {
            checkpoints.clear(); checkpoints.addAll(previous);
            for(var item:current.entrySet()) try { restore(item.getKey(),item.getValue()); }
            catch(IOException rollback) { failure.addSuppressed(rollback); }
            throw failure;
        }
        return new RewindResult(messages,restored.keySet().stream().map(workspace::relativize).map(Path::toString).toList());
    }
    private Path resolve(String relative) throws IOException {
        Path path = new ToolContext(workspace, true, false).resolve(relative,false);
        Path relativePath=workspace.relativize(path);
        // Production worktrees live under .mewcode/worktrees/<name>; their source files are ordinary user files.
        int start=relativePath.getNameCount()>3
                && relativePath.getName(0).toString().equalsIgnoreCase(".mewcode")
                && relativePath.getName(1).toString().equalsIgnoreCase("worktrees") ? 3 : 0;
        for(int i=start;i<relativePath.getNameCount();i++) {
            Path segment=relativePath.getName(i);
            String value=segment.toString();
            if(value.equalsIgnoreCase(".git") || value.equalsIgnoreCase(".mewcode"))
                throw new IOException("Internal metadata is not a rewindable file");
        }
        return path;
    }
    private static byte[] read(Path path) throws IOException {
        if(!Files.exists(path,LinkOption.NOFOLLOW_LINKS)) return null;
        if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)||Files.size(path)>MAX_FILE_BYTES) throw new IOException("Not a checkpointable regular file: " + path);
        return Files.readAllBytes(path);
    }
    private void persist() throws IOException { atomicWrite(journal,JSON.writeValueAsBytes(new State(nextId,checkpoints))); }
    private static void restore(Path path,byte[] content) throws IOException {
        if(content==null) Files.deleteIfExists(path); else atomicWrite(path,content);
    }
    private static void atomicWrite(Path path,byte[] content) throws IOException {
        Files.createDirectories(path.getParent());
        Path temporary=Files.createTempFile(path.getParent(),".star-checkpoint-",".tmp");
        try {
            try(var channel=java.nio.channels.FileChannel.open(temporary,StandardOpenOption.WRITE)) {
                var buffer=java.nio.ByteBuffer.wrap(content);
                while(buffer.hasRemaining()) channel.write(buffer);
                channel.force(true);
            }
            if(Files.exists(path,LinkOption.NOFOLLOW_LINKS) && Files.getFileStore(path).supportsFileAttributeView("posix"))
                Files.setPosixFilePermissions(temporary,Files.getPosixFilePermissions(path,LinkOption.NOFOLLOW_LINKS));
            try { Files.move(temporary,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING); }
            catch(AtomicMoveNotSupportedException ignored) { Files.move(temporary,path,StandardCopyOption.REPLACE_EXISTING); }
        } finally { Files.deleteIfExists(temporary); }
    }
}
