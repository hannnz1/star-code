# Java behavior and assertion audit

This inventory maps behavior contracts, not identical implementations. Baseline tests are retained as helper evidence; active durable tests are listed first. Passing counts come only from the linked JUnit run, never from this generator.

The clean Windows/no-JVM/file-symlink release gate is still open. Changed contracts below are explicit replacements, not claims of Java option or UI identity.

## agent

Durable sequential tool rounds, shared limits, cancellation and verified completion replace the in-process loop. No dontAsk permission bypass or parallel write dispatch.

Active implementation: `src/muse/agent;src/muse/tasks/worker.py`

Regression files: `tests/muse/unit/test_agent_loop.py;tests/muse/unit/test_agent_completion.py;tests/test_active_group_budget.py`

## command

Slash commands use the shared HTTP task service. Rewind files and conversation are explicit separate actions. Worktree mutations and skill execution are approved task tools, not direct slash side effects.

Active implementation: `src/muse/terminal.py;src/muse/compat_cli.py`

Regression files: `tests/test_terminal_service.py;tests/test_terminal_context.py;tests/test_compat_entry.py;tests/test_commands.py`

## config

Preserve original model, endpoint, proxy, credential source and limits. Explicit missing environment keys never fall back to another provider.

Active implementation: `src/muse/config.py;mewcode/config.py`

Regression files: `tests/test_starcode_provider.py;tests/muse/unit/test_config.py;tests/test_baseline_config_protection.py`

## context

Deterministic complete-turn compaction and durable offloads replace model-written tagged summaries. Java summary-tag/retry parser is intentionally not in the active execution path.

Active implementation: `src/muse/agent/context.py;src/muse/tools/registry.py`

Regression files: `tests/muse/unit/test_context.py;tests/test_terminal_context.py;tests/test_context.py;tests/test_context_window.py`

## hook

Configured events use durable receipts, approvals and child jobs. Startup/shutdown mean task-runtime boundaries; shell/HTTP hooks require approval. No unapproved global hooks.

Active implementation: `src/muse/extensions/hooks.py;src/muse/agent/loop.py`

Regression files: `tests/test_durable_hooks.py;tests/test_hook_lifecycle.py;tests/test_async_hook_job.py;tests/test_extension_receipts.py;tests/test_hooks.py`

## instructions

Registered workspace instructions and bounded includes are snapshotted. Implicit home/ancestor traversal is removed to preserve the workspace boundary.

Active implementation: `src/muse/agent/instructions.py`

Regression files: `tests/test_project_guidance.py`

## llm

Responses, Chat Completions and Anthropic structured streams require terminal evidence. Durable checkpoints preserve complete exchanges; public errors omit provider response secrets.

Active implementation: `src/muse/providers;src/muse/tasks/conversation.py`

Regression files: `tests/muse/unit/test_provider_stream.py;tests/test_durable_anthropic.py;tests/test_conversation_checkpoints.py;tests/test_serialization.py`

## mcp

Lazy explicit configured-server discovery, bounded schemas and separately approved calls replace automatic readOnly remote execution. HTTP/stdio real local fixtures cover transport; model never grants remote authority.

Active implementation: `src/muse/extensions/mcp.py;src/muse/extensions/stdio.py;mewcode/mcp/client.py`

Regression files: `tests/test_durable_mcp.py;tests/test_mcp_http_integration.py;tests/test_mcp_transport_safety.py;tests/test_mcp_pagination.py;tests/test_mcp.py`

## memory

User/project SQLite memories replace Markdown index authority and implicit asynchronous model writes. Save/delete are explicit approved tools; secret and scope checks remain enforced.

Active implementation: `src/muse/memory/service.py;src/muse/extensions/memory.py`

Regression files: `tests/test_durable_memory_tools.py;tests/muse/integration/test_artifacts_documents_memory.py;tests/test_memory.py`

## permission

Workspace deny rules and digest-bound per-action approvals replace reusable broad command grants and bypass modes. Windows process containment is not an OS filesystem/network sandbox. File-symlink clean-host gate remains open.

Active implementation: `src/muse/permissions;src/muse/tasks/repository.py`

Regression files: `tests/muse/unit/test_permissions.py;tests/test_permissions.py;tests/muse/integration/test_workspace_tools.py;tests/test_review_regressions.py`

## prompt

Deterministic role/task instructions, selected memories and tool restrictions replace Java prompt modules. No model/provider override through skill or role metadata.

Active implementation: `src/muse/agent/instructions.py;src/muse/agent/loop.py`

Regression files: `tests/test_project_guidance.py;tests/test_durable_roles.py;tests/muse/unit/test_agent_completion.py;tests/muse/unit/test_provider_stream.py`

## session

Transactional SQLite events/checkpoints and hash-checked file journals replace JSONL session authority. Damaged/unknown effects are retained for explicit reconciliation, never silently skipped or replayed.

Active implementation: `src/muse/tasks;src/muse/storage;src/muse/tools/files.py`

Regression files: `tests/test_conversation_checkpoints.py;tests/test_state_backup.py;tests/muse/integration/test_reconciliation.py;tests/muse/integration/test_migration.py;tests/muse/integration/test_crash_process.py`

## skill

Lazy Markdown/YAML skills, explicit global skill_roots, source-bound fork and pinned archive installation. Selected original model is mandatory; conflicting provider metadata is rejected.

Active implementation: `src/muse/extensions/skills.py;src/muse/extensions/skill_install.py`

Regression files: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

## subagent

Builtin/project roles and isolated role work inherit capability intersections and shared budgets. All children are persistent tasks; foreground blocking and tmux runner spawning are replaced by task waiting/review.

Active implementation: `src/muse/extensions/roles.py;src/muse/tasks/delegation.py`

Regression files: `tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py`

## task

Persisted queue, lease fencing, child IDs, messages, automatic parent wakeup and cancellation replace in-memory task futures. Client timeout leaves work running.

Active implementation: `src/muse/tasks;src/muse/extensions/teams.py`

Regression files: `tests/test_durable_delegation.py;tests/test_durable_teams.py;tests/test_extension_receipts.py;tests/muse/integration/test_recovery.py`

## team

Root-task groups, SQLite inbox/board, revisions/dependencies and persisted children replace team directories, file locks and pane backends. Terminal/web view the same group; no separate teammate CLI authority.

Active implementation: `src/muse/tasks/teams.py;src/muse/extensions/teams.py;src/muse/tasks/delegation.py`

Regression files: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

## tool

Bounded file/search/edit/command tools share one dispatch and approval path. Structured exit codes, process-tree cancellation and verification prevent false success. Unsupported OS sandbox is not claimed.

Active implementation: `src/muse/tools;src/muse/permissions`

Regression files: `tests/muse/integration/test_workspace_tools.py;tests/test_shell_lifecycle.py;tests/test_mutation_verification.py;tests/test_edit_file.py;tests/muse/integration/test_shell_runtime.py`

## ui

Textual terminal and React workspace replace Java terminal rendering. Original slash concepts remain discoverable; Windows paths stay in JSON/argv rather than shell interpolation.

Active implementation: `src/muse/tui.py;src/muse/terminal.py;frontend/src/main.tsx`

Regression files: `tests/test_durable_tui.py;tests/test_terminal_service.py;tests/test_terminal_context.py;tests/muse/integration/test_frontend.py;tests/test_commands.py`

## worktree

Exact-commit sibling checkout, role restrictions, reviewed fast-forward merge and clean merged retirement. No copying private ignored files, auto-running local hooks, auto-deleting work, or implicit conflict merge.

Active implementation: `src/muse/extensions/worktrees.py`

Regression files: `tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py`

## starcode

Python console/module entry plus API/Worker replace JVM/Gradle launch. Wheel bundles the web UI. Independent no-JVM Windows acceptance remains pending.

Active implementation: `src/muse/cli.py;src/muse/compat_cli.py;pyproject.toml;hatch_build.py`

Regression files: `tests/test_compat_entry.py;tests/test_distribution_integration.py;tests/muse/integration/test_launcher.py`

### AgentLoopTest.java

Key assertion intents: `performsMultipleToolRoundsUntilNaturalCompletionAndAccumulatesUsage`, `stopsAtIterationLimit`, `stopsBeforeExecutingCallsBeyondToolLimit`, `providerFailureBecomesErrorOutcomeAndEvent`, `emptyModelResponseIsAnError`, `cancellingAsyncRunInterruptsProviderWait`, `stopsAfterConsecutiveUnknownToolRounds`, `cancelledBeforeStartDoesNotCallProvider`, `planModeExposesOnlyReadOnlyTools`, `readOnlyBatchRunsConcurrentlyButPublishesResultsInOrder`, `permissionDenialIsFedBackAndLoopContinues`, `preToolHookBlocksWithStructuredResultAndLoopContinues`, `hookPromptIsInjectedOnceIntoNextProviderRequest`, `childBuilderUsesRolePromptFiltersToolsAndBlocksNestedAgent`, `dontAskApprovesFallbackWithoutOpeningInteractiveApprover`, `configuredBudgetCanCompletePastTenTurnsAndIsVisibleToModel`, `configuredBudgetStillStopsUnfinishedExecution`

Evidence: `tests/muse/unit/test_agent_loop.py;tests/muse/unit/test_agent_completion.py;tests/test_active_group_budget.py`

### CommandCompletionTest.java

Key assertion intents: `filtersMovesAndHides`, `staysActiveForNoMatchesAndRejectsMultiline`

Evidence: `tests/test_terminal_service.py;tests/test_terminal_context.py;tests/test_compat_entry.py;tests/test_commands.py`

### CommandDispatchTest.java

Key assertion intents: `parsesZeroArgumentCommands`

Evidence: `tests/test_terminal_service.py;tests/test_terminal_context.py;tests/test_compat_entry.py;tests/test_commands.py`

### CommandRegistryTest.java

Key assertion intents: `builtinsAreSortedVisibleAndCaseInsensitive`, `rejectsNameAndAliasConflictsAtRegistration`, `completionUsesVisibleCanonicalNamesOnly`, `localAndPromptCommandsUseOnlyContextContract`, `removesOnlyDynamicSkillCommands`, `rewindArgumentsGoToLocalContextWithoutAModelPrompt`

Evidence: `tests/test_terminal_service.py;tests/test_terminal_context.py;tests/test_compat_entry.py;tests/test_commands.py`

### WorktreeCommandTest.java

Key assertion intents: `dispatchesAllSubcommandsWhileOtherCommandsRemainZeroArgument`, `unavailableManagerAndUnsafeArgumentsAreFriendly`

Evidence: `tests/test_terminal_service.py;tests/test_terminal_context.py;tests/test_compat_entry.py;tests/test_commands.py`

### ConfigLoaderTest.java

Key assertion intents: `acceptsMewProtocolNamesWithoutChangingOtherProviderSettings`, `mainAgentBudgetsHaveBoundedDefaultsAndStrictOverrides`, `missingFileIsReadableConfigurationError`, `contextWindowUsesProtocolDefaultAndAcceptsOverride`

Evidence: `tests/test_starcode_provider.py;tests/muse/unit/test_config.py;tests/test_baseline_config_protection.py`

### CompressionReliabilityTest.java

Key assertion intents: `completeSummary`, `quotedProtocolMarkersArePreservedAsContent`, `quotedClosingMarkerCannotCompleteTruncatedSummary`, `quotingDoesNotHideRealDuplicateBlocks`, `unmatchedBacktickDoesNotSwallowRealClosingMarker`, `ignoresSurroundingExplanations`, `fencedBlockAndMissingNoncriticalFence`, `tagWhitespaceAndMarkdownHeadings`, `missingClosingMarkerFailsEvenWithAllSections`, `emptySummaryFails`, `truncatedBeforePendingTasksFailsEvenWithClosingMarker`, `malformedAndDuplicateBlocksFail`, `sectionBodiesMustExist`, `reorderedSectionsFail`, `rejectsUnboundedOutput`, `invalidThenSuccessfulRetryKeepsOriginalHistory`, `rateLimitDoesNotEnterSummaryFormatRetryOrMutateHistory`, `failedRetryDoesNotMutateConversationOrUsageAnchor`, `responsesStreamMustHaveTerminalEvidenceEvenWhenTextIsValid`, `authenticationFailureIsNotRetriedOrLoggedWithSecrets`, `contextLengthRetriesAreBoundedAndKeepGroupsIntact`

Evidence: `tests/muse/unit/test_context.py;tests/test_terminal_context.py;tests/test_context.py;tests/test_context_window.py`

### ContextManagerTest.java

Key assertion intents: `missingProviderUsageKeepsRealCompactionThresholdReachable`, `largeResultIsOffloadedWithStablePreviewAndIdempotentFile`, `aggregateBudgetOffloadsMinimumLargestResult`, `utf8PreviewNeverExceedsByteAndLineLimits`, `replacementDecisionSurvivesManagerReconstruction`, `extractsOnlySummaryAndCompactionUsesNoTools`, `compactRecoveryDoesNotReinjectDeferredSchemas`, `responsesCacheBreakdownDoesNotTriggerPrematureCompaction`, `anthropicCacheCountsRemainAdditive`, `estimateUsesReplacementAnchorRatherThanAccumulatingUsage`, `summaryRetryGroupsKeepAssistantToolRoundTripsTogether`

Evidence: `tests/muse/unit/test_context.py;tests/test_terminal_context.py;tests/test_context.py;tests/test_context_window.py`

### DefaultHookActionExecutorTest.java

Key assertion intents: `promptAndTemplateRenderingWorkWithoutExternalServices`, `shellExitTwoBlocksOnlyBlockingEvents`, `httpDecisionCanBlockAndInvalidResponseFailsOpen`

Evidence: `tests/test_durable_hooks.py;tests/test_hook_lifecycle.py;tests/test_async_hook_job.py;tests/test_extension_receipts.py;tests/test_hooks.py`

### HookEngineTest.java

Key assertion intents: `exposesExactlyElevenEventsAndOnlyTwoAreBlocking`, `blockingShortCircuitsAndReturnsPromptsInDeclarationOrder`, `onlyOnceResetsForNewSession`, `payloadJsonAndNestedFieldsAreStable`

Evidence: `tests/test_durable_hooks.py;tests/test_hook_lifecycle.py;tests/test_async_hook_job.py;tests/test_extension_receipts.py;tests/test_hooks.py`

### HookLoaderTest.java

Key assertion intents: `loadsBothTiersInOrderAndSkipsDuplicateAndInvalidRules`, `malformedYamlDoesNotThrow`

Evidence: `tests/test_durable_hooks.py;tests/test_hook_lifecycle.py;tests/test_async_hook_job.py;tests/test_extension_receipts.py;tests/test_hooks.py`

### InstructionLoaderTest.java

Key assertion intents: `loadsThreeLayersInPriorityOrderAndExpandsIncludes`, `detectsCycleDepthAndPathEscape`

Evidence: `tests/test_project_guidance.py`

### ConversationTest.java

Key assertion intents: `absentProtocolStateSurvivesJsonRoundTripForEveryRole`, `populatedProtocolStateAndToolExchangeSurviveJsonRoundTrip`, `onlyCommitsSuccessfulPair`, `invokesAppendAndReplaceCallbacksOutsideStorageOperations`, `commitsCompleteToolExchangesInProtocolOrder`

Evidence: `tests/muse/unit/test_provider_stream.py;tests/test_durable_anthropic.py;tests/test_conversation_checkpoints.py;tests/test_serialization.py`

### ErrorClassificationTest.java

Key assertion intents: `mewOpenAiProtocolAliasUsesResponses`, `recognizesCommonContextLimitMessages`

Evidence: `tests/muse/unit/test_provider_stream.py;tests/test_durable_anthropic.py;tests/test_conversation_checkpoints.py;tests/test_serialization.py`

### ProtocolToolFlowTest.java

Key assertion intents: `openAiParsesFragmentedToolCallAndSendsOutput`, `anthropicParsesFragmentedToolCallAndSendsToolResult`, `openAiReplaysStructuredToolHistoryOnANewUserTurn`, `anthropicReplaysStructuredToolHistoryOnANewUserTurn`, `openAiStreamRateLimitsKeepTheirClassification`, `anthropicStreamRateLimitsKeepTheirClassification`, `chatCompletionsReplaysFragmentedCallsHistoryAndUsage`, `chatCompletionsRejectsTruncatedStreamsAndPropagatesRateLimits`

Evidence: `tests/muse/unit/test_provider_stream.py;tests/test_durable_anthropic.py;tests/test_conversation_checkpoints.py;tests/test_serialization.py`

### SseReaderTest.java

Key assertion intents: `joinsDataLinesAndEmitsEvents`

Evidence: `tests/muse/unit/test_provider_stream.py;tests/test_durable_anthropic.py;tests/test_conversation_checkpoints.py;tests/test_serialization.py`

### McpClientFeatureTest.java

Key assertion intents: `projectServerCompletelyOverridesUserServerAndExpandsOnlySecrets`, `invalidFilesAndServersAreSkippedWithWarnings`, `undefinedEnvironmentVariableBecomesEmptyAndWarns`, `adapterNamespacesSchemaReadOnlyAndTextResults`, `adapterConvertsRemoteFailureToStructuredToolError`, `registrationSkipsInvalidNamesAndReplacesDuplicateWithinNamespace`, `readOnlyMcpToolUsesDefaultAutoAllowAndWildcardRulesMatch`, `officialSdkCompletesHttpInitializeListAndCallWithCustomHeader`, `officialSdkCompletesStdioInitializeListCallAndEnvironmentInjection`

Evidence: `tests/test_durable_mcp.py;tests/test_mcp_http_integration.py;tests/test_mcp_transport_safety.py;tests/test_mcp_pagination.py;tests/test_mcp.py`

### McpLazyLoadingTest.java

Key assertion intents: `catalogIsLazyAndPerAgentAndFullModeIsAvailable`, `hiddenToolsCannotBeDiscoveredOrExecutedAndInvalidSearchDoesNotLoad`, `agentRefreshesSchemasExecutesRemoteAndKeepsActivationOnNextTurn`, `discoveryDoesNotAuthorizeRemoteSideEffects`, `planCannotInvokeAnUnadvertisedMutatingMcpTool`

Evidence: `tests/test_durable_mcp.py;tests/test_mcp_http_integration.py;tests/test_mcp_transport_safety.py;tests/test_mcp_pagination.py;tests/test_mcp.py`

### MemoryManagerTest.java

Key assertion intents: `explicitMemoryRequestUpdatesIndexAsynchronously`, `suppressionSignalSkipsUpdate`, `listFilesIncludesMarkdownIndexesAndSortsEachLevel`

Evidence: `tests/test_durable_memory_tools.py;tests/muse/integration/test_artifacts_documents_memory.py;tests/test_memory.py`

### MemoryStoreTest.java

Key assertion intents: `createsUpdatesAndDeletesNotesWhileRebuildingIndex`, `rejectsUnsafeNamesAndTruncatesUtf8AtByteBoundary`

Evidence: `tests/test_durable_memory_tools.py;tests/muse/integration/test_artifacts_documents_memory.py;tests/test_memory.py`

### PermissionSystemTest.java

Key assertion intents: `blacklistCannotBeBypassed`, `sandboxRejectsTraversalAndAllowsNewNestedWorkspacePath`, `ruleMatchingSupportsExactGlobAndDenyPriority`, `localRulesOverrideProjectAndUserRules`, `modeMatrixOnlyAllowsOrAsks`, `deniedApprovalReturnsStructuredDenialAndDoesNotExecute`, `invalidConfigurationDegradesToEmptyRules`

Evidence: `tests/muse/unit/test_permissions.py;tests/test_permissions.py;tests/muse/integration/test_workspace_tools.py;tests/test_review_regressions.py`

### SessionApprovalTest.java

Key assertion intents: `repeatedFileEditsReuseExplicitGrantWithoutWritingConfig`, `cacheIsScopedToActorDirectoryModeAndExactRemoteArguments`, `changingCommandCannotReuseBuildPermission`, `resetCancellationAndSafetyChecksRemainEffective`, `resetWhilePromptIsOpenDoesNotPopulateNewSession`

Evidence: `tests/muse/unit/test_permissions.py;tests/test_permissions.py;tests/muse/integration/test_workspace_tools.py;tests/test_review_regressions.py`

### ValueMatcherTest.java

Key assertion intents: `permissionSyntaxSupportsExactRegexGlobAndNestedNot`, `structuredNotWrapsAnyMatcher`, `invalidRegexAndMissingInnerFailAtLoadTime`

Evidence: `tests/muse/unit/test_permissions.py;tests/test_permissions.py;tests/muse/integration/test_workspace_tools.py;tests/test_review_regressions.py`

### SystemPromptEngineeringTest.java

Key assertion intents: `modulesAreSortedAndEmptySlotsAreSkipped`, `stablePromptIsDeterministicAndReinforcesRules`, `injectsInstructionsAndMemoryInDeclaredPriorityOrder`, `skillsCatalogUsesStableOptionalModule`, `planReminderUsesFullCompactAndPeriodicFullForms`, `cacheUsageAccumulates`

Evidence: `tests/test_project_guidance.py;tests/test_durable_roles.py;tests/muse/unit/test_agent_completion.py;tests/muse/unit/test_provider_stream.py`

### FileHistoryTest.java

Key assertion intents: `actualFileToolsRestorePreviousContentAndRemoveNewFileAfterReload`, `externalEditsRejectEntireRewindBeforeAnyFileChanges`, `multipleCheckpointsAndConversationOnlyDoNotLoseFileHistory`, `worktreeContextsShareJournalAndMetadataCannotBeRewritten`

Evidence: `tests/test_conversation_checkpoints.py;tests/test_state_backup.py;tests/muse/integration/test_reconciliation.py;tests/muse/integration/test_migration.py;tests/muse/integration/test_crash_process.py`

### SessionPersistenceTest.java

Key assertion intents: `writesJsonlAndLoadsOnlyContentAfterLastCompact`, `skipsDamagedLinesAndCatalogIgnoresOldIds`, `cleanupDeletesOnlyExpiredNewFormatDirectories`, `structuredToolHistoryRoundTripsLosslessly`

Evidence: `tests/test_conversation_checkpoints.py;tests/test_state_backup.py;tests/muse/integration/test_reconciliation.py;tests/muse/integration/test_migration.py;tests/muse/integration/test_crash_process.py`

### GitHubSkillInstallerTest.java

Key assertion intents: `parsesApprovedGitHubUrls`, `rejectsUnapprovedOrUnsafeUrls`

Evidence: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

### LoadSkillToolTest.java

Key assertion intents: `loadsKnownSkillAsReadOnlyAndReturnsStructuredUnknownError`

Evidence: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

### SkillCatalogTest.java

Key assertion intents: `discoversMetadataLazilyAndReloadsBodyOnEveryGetFull`, `supportsYamlPromptFormatAndLaterRegistrationWins`, `skipsInvalidSkillWithoutLosingValidSibling`, `acceptsUtf8BomWrittenByWindowsPowerShell`

Evidence: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

### SkillExecutorTest.java

Key assertion intents: `substitutesArgumentsAndBuildsSeeds`, `inlineActivatesAndRecordsInvocation`, `recentForkSeedDoesNotSplitToolPair`, `forkDelegatesWithMetadataAndSelectedSeed`

Evidence: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

### SkillInvocationAuditTest.java

Key assertion intents: `appendsTraceableSessionScopedRecords`

Evidence: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

### SkillProviderResolverTest.java

Key assertion intents: `reusesCurrentAndSupportsModelOrProviderOverrides`

Evidence: `tests/test_durable_skills.py;tests/test_skill_install.py;tests/test_extension_receipts.py;tests/test_skills.py`

### ForkMessagesTest.java

Key assertion intents: `copiesParentAndAddsStableBoilerplateTask`

Evidence: `tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py`

### SubAgentCatalogTest.java

Key assertion intents: `loadsBuiltinsAndProjectOverridesUserCaseInsensitively`, `badUserDefinitionDoesNotHideBuiltins`

Evidence: `tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py`

### SubAgentDefinitionParserTest.java

Key assertion intents: `parsesCompleteDefinitionAndCanonicalizesName`, `rejectsMissingRequiredFieldsAndBadNames`, `invalidOptionalEnumsDegradeSafely`

Evidence: `tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py`

### SubAgentToolFilterTest.java

Key assertion intents: `definedAgentsCannotSeeAgentAndDefinitionsFurtherNarrow`, `backgroundKeepsOnlyBaseAndMcpTools`, `forkKeepsAgentDefinitionButRuntimeGuardRemainsRequired`

Evidence: `tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py`

### SubAgentToolTest.java

Key assertion intents: `schemaIsStableAndDefinedRoleRunsSynchronously`, `teamNameDelegatesToTeamHookWithoutLaunchingOrdinaryChild`, `unknownRoleAndDisabledForkAreStructuredErrors`, `explicitBackgroundReturnsTaskIdImmediately`, `foregroundTimeoutAdoptsTheSameRunningSession`, `worktreeRoleWritesOnlyInsideAnIsolatedCopyAndForcesForeground`

Evidence: `tests/test_durable_roles.py;tests/test_project_guidance.py;tests/test_durable_delegation.py;tests/test_durable_worktrees.py;tests/test_subagent.py`

### SubAgentTaskManagerTest.java

Key assertion intents: `launchCompletesNotifiesAndSupportsFollowUp`, `failedChildIsIsolated`

Evidence: `tests/test_durable_delegation.py;tests/test_durable_teams.py;tests/test_extension_receipts.py;tests/muse/integration/test_recovery.py`

### TaskToolsTest.java

Key assertion intents: `listGetStopAndSendMessageExposeStructuredResults`, `unknownTaskIsAnError`

Evidence: `tests/test_durable_delegation.py;tests/test_durable_teams.py;tests/test_extension_receipts.py;tests/muse/integration/test_recovery.py`

### TaskWaitTest.java

Key assertion intents: `teamScopeResolvesOnlyItsOwnExecutionAndKeepsSharedTasks`, `waitReturnsCompletedResultWithoutAnotherModelPoll`, `timeoutAndCancellationDoNotStopWorker`, `rejectsInvalidWaitWithoutSilentCoercion`

Evidence: `tests/test_durable_delegation.py;tests/test_durable_teams.py;tests/test_extension_receipts.py;tests/muse/integration/test_recovery.py`

### AgentNameRegistryTest.java

Key assertion intents: `maintainsBidirectionalMappingsAcrossReplacement`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### PaneBackendTest.java

Key assertion intents: `tmuxBuildsRunnerCommandAndReturnsPane`, `itermPassesArgumentsWithoutOneConcatenatedShellCommand`, `memberArgumentsNeverExposeRawPrompt`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### BackendDetectorTest.java

Key assertion intents: `tmuxEnvironmentWinsAndEmptyEnvironmentFallsBack`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### CoordinatorModeTest.java

Key assertion intents: `requiresConfigAndEnvironmentSwitches`, `whitelistExcludesDirectFileWrites`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### MailboxTest.java

Key assertion intents: `writesReadsAndMarksUnreadMessages`, `concurrentWritersDoNotLoseMessages`, `staleLockCanBeReclaimed`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### TeamManagerTest.java

Key assertion intents: `createsSanitizesSuffixesReloadsAndDeletes`, `memberMutationReloadsDiskAndActiveMembersProtectDelete`, `planCompletionRequestsApprovalAndApprovalSwitchesMode`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### TeamMemberOptionsTest.java

Key assertion intents: `parsesStableRunnerProtocol`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### TeamTaskStoreTest.java

Key assertion intents: `createsFiltersAndMaintainsDependencyGraph`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### TeamToolsTest.java

Key assertion intents: `sevenStableToolNamesSupportTeamWorkflowWithoutDuplicates`

Evidence: `tests/test_team_board.py;tests/test_durable_teams.py;tests/test_durable_delegation.py;tests/test_team_protocol.py;tests/test_teams.py`

### ShellRuntimeTest.java

Key assertion intents: `shellTextRemainsOneArgumentOnEveryPlatform`, `requiredSandboxFailsClosedOnUnsupportedPlatformOrInvalidMode`, `linuxSandboxRestrictsWritesAndNetworkingByDefault`, `macProfileKeepsNetworkOptInAndEscapesPaths`

Evidence: `tests/muse/integration/test_workspace_tools.py;tests/test_shell_lifecycle.py;tests/test_mutation_verification.py;tests/test_edit_file.py;tests/muse/integration/test_shell_runtime.py`

### ToolSystemTest.java

Key assertion intents: `registersSixTools`, `mutationsAreDisabledByDefaultContext`, `writesNestedFileAndReadsWithLineNumbers`, `rejectsWorkspaceEscapeAndMissingFile`, `editRequiresExactlyOneMatch`, `globAndSearchReturnRelativeLocations`, `doubleStarGlobAlsoMatchesWorkspaceRoot`, `bashReturnsOutputAndNonZeroAsStructuredResult`, `rejectsLargeFileAndLimitsLongText`, `globAndSearchLimitLargeResultSets`, `bashTimeoutReturnsStructuredFailure`, `registryAppliesUniformPerToolTimeout`, `explicitCwdScopesAllCoreToolsWithoutChangingSchemas`

Evidence: `tests/muse/integration/test_workspace_tools.py;tests/test_shell_lifecycle.py;tests/test_mutation_verification.py;tests/test_edit_file.py;tests/muse/integration/test_shell_runtime.py`

### MarkdownRendererTest.java

Key assertion intents: `rendersHeadingsCodeAndBold`, `rendersUnorderedListsAsBullets`

Evidence: `tests/test_durable_tui.py;tests/test_terminal_service.py;tests/test_terminal_context.py;tests/muse/integration/test_frontend.py;tests/test_commands.py`

### WindowsPathInputTest.java

Key assertion intents: `parserPreservesWindowsBackslashes`

Evidence: `tests/test_durable_tui.py;tests/test_terminal_service.py;tests/test_terminal_context.py;tests/muse/integration/test_frontend.py;tests/test_commands.py`

### GitHelperTest.java

Key assertion intents: `processIsNonInteractiveAndFilesystemHeadResolutionWorks`, `changeDetectionIsFailClosed`

Evidence: `tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py`

### SessionStoreTest.java

Key assertion intents: `roundTripsSnakeCaseJsonAndClearWritesNull`

Evidence: `tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py`

### WorktreeManagerTest.java

Key assertion intents: `rejectsNonRepository`, `createsNestedNamesRecoversMetadataAndRejectsDuplicates`, `lifecycleProtectsChangesAndPersistsSession`, `autoCleanupAndSweepOnlyRemoveCleanTemporaryTrees`, `postCreationCopiesLocalFilesAndIncludedIgnoredFiles`, `damagedSessionIsClearedWithoutBlockingConstruction`, `hooksUsePerWorktreeConfigWhenRepositoryEnablesIt`

Evidence: `tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py`

### WorktreeSlugTest.java

Key assertion intents: `validatesAndFlattensSafeNames`, `rejectsTraversalAndShellCharacters`, `temporaryNamesHaveTheDocumentedShape`

Evidence: `tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py`

### WorktreeTestSupport.java

Key assertion intents: Shared Git test support.

Evidence: `tests/test_durable_worktrees.py;tests/test_worktree_lifecycle.py;tests/test_worktree.py`

