package com.starcode.worktree;

import java.io.IOException;

public final class WorktreeHasChangesException extends IOException {
    public WorktreeHasChangesException() {
        super("Worktree 存在未提交修改或创建后的新提交；请先处理变更，或显式使用 --discard");
    }
}
