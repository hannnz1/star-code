package com.starcode.task;

import com.starcode.agent.CancellationToken;
import com.starcode.llm.TokenUsage;
import com.starcode.subagent.SubAgentSession;
import com.starcode.permission.PermissionMode;
import java.time.Instant;

/** Thread-safe mutable lifecycle record retained for the process lifetime. */
public final class BackgroundTask {
    private final String id;
    private final String name;
    private final SubAgentSession session;
    private final String initialTask;
    private final Instant startTime;
    private final TaskMetrics metrics;
    private volatile TaskStatus status = TaskStatus.RUNNING;
    private volatile String result = "";
    private volatile Throwable error;
    private volatile Instant endTime;
    private volatile CancellationToken cancellation;

    BackgroundTask(String id, String name, SubAgentSession session, String initialTask,
                   CancellationToken cancellation, TaskMetrics metrics) {
        this.id = id;
        this.name = name == null ? "" : name;
        this.session = session;
        this.initialTask = initialTask;
        this.cancellation = cancellation;
        this.metrics = metrics;
        this.startTime = Instant.now();
    }

    public String id() { return id; }
    public String name() { return name; }
    public String initialTask() { return initialTask; }
    public TaskStatus status() { return status; }
    public String result() { return result; }
    public Throwable error() { return error; }
    public Instant startTime() { return startTime; }
    public Instant endTime() { return endTime; }
    public int toolCount() { return metrics.toolCount(); }
    public String lastActivity() { return metrics.lastActivity(); }
    public TokenUsage usage() { return metrics.usage(); }
    public PermissionMode permissionMode() { return session.permissionMode(); }
    SubAgentSession session() { return session; }
    CancellationToken cancellation() { return cancellation; }
    void cancellation(CancellationToken value) { cancellation = value; }
    void running() { status = TaskStatus.RUNNING; endTime = null; error = null; }
    void completed(String value) { result = value == null ? "" : value; status = TaskStatus.COMPLETED; endTime = Instant.now(); }
    void failed(Throwable value) { error = value; status = TaskStatus.FAILED; endTime = Instant.now(); }
    void cancelled() { status = TaskStatus.CANCELLED; endTime = Instant.now(); }
}
