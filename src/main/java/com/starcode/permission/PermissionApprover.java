package com.starcode.permission;

import com.starcode.agent.CancellationToken;

@FunctionalInterface
public interface PermissionApprover {
    ApprovalChoice approve(PermissionRequest request, CancellationToken cancellation) throws InterruptedException;
}
