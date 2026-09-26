# Data Model — Receipts

## Overview

All persistence uses SQLAlchemy ORM with SQLite (default) or PostgreSQL. Tables are created via `Base.metadata.create_all()` on startup.

---

## Core Review Models

### `repository`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `name` | str(255) UNIQUE | Repository identifier |
| `url` | str(512) | Remote URL (optional) |
| `local_path` | str(512) | Local filesystem path (optional) |
| `created_at` | datetime | |

### `pull_request`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `repo_id` | FK→repository | |
| `number` | int | PR number |
| `title` | str(512) | PR title |
| `author` | str(255) | Author name |
| `base_branch` | str(255) | Target branch |
| `head_branch` | str(255) | Source branch |
| `commit_sha` | str(64) | HEAD commit SHA |
| `created_at` | datetime | |

### `review_run`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pr_id` | FK→pull_request | |
| `risk_level` | enum(RiskLevelEnum) | low/medium/high/critical |
| `status` | enum(ReviewStatusEnum) | pending/running/completed/failed |
| `confidence` | float | 0.0–1.0 |
| `verdict` | enum(VerdictEnum) | SAFE/BUG_DETECTED/ESCALATE |
| `started_at` | datetime | |
| `completed_at` | datetime | |
| `elapsed_ms` | int | |

### `agent_execution`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `agent_type` | enum(AgentTypeEnum) | test_runner/catching_test/documentation_check/history_check |
| `status` | enum(AgentStatusEnum) | pending/running/completed/error/timeout/insufficient_evidence |
| `started_at` | datetime | |
| `completed_at` | datetime | |

### `receipt`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `agent_execution_id` | FK→agent_execution | |
| `title` | str(255) | |
| `command` | str(1024) | Exact command run |
| `test_ref` | str(255) | Test name/path |
| `result_summary` | str(64) | PASS or FAIL |
| `raw_output` | text | Real stdout+stderr |
| `file_ref` | str(512) | |
| `severity` | enum(SeverityEnum) | PASS/INFO/LOW/MEDIUM/HIGH/CRITICAL |
| `confidence` | float | |
| `bob_evidence_ref` | text | Extension point — never auto-populated |
| `created_at` | datetime | |

### `review_event`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `event_type` | str(64) | e.g. agent.started |
| `agent_type` | str(64) | |
| `payload` | text | JSON payload |
| `created_at` | datetime | |

---

## Audit Model

### `audit_event`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run (nullable) | |
| `event_type` | str(64) | |
| `payload` | text | Raw payload (display) |
| `canonical_payload` | text | Deterministic JSON (hash input) |
| `integrity_hash` | str(128) | SHA-256 hash |
| `prev_hash` | str(128) | Previous event hash |
| `entity_ref` | str(128) | Optional reference |
| `sequence` | int | Monotonic order number |
| `created_at` | datetime | |

---

## Immunity Pipeline Models

### `immunity_pipeline`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `status` | enum(ImmunityStatusEnum) | pending/running/passed/failed/blocked/escalated |
| `source_receipt_ids` | text | JSON list of receipt IDs |
| `current_stage` | str(64) | |
| `created_at` | datetime | |
| `updated_at` | datetime | |

### `immunity_stage`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pipeline_id` | FK→immunity_pipeline | |
| `stage_type` | enum(StageTypeEnum) | reproduce/root_cause/fix/verify/regression_test/sibling_hunt/documentation/pattern |
| `status` | enum(ImmunityStatusEnum) | |
| `started_at` | datetime | |
| `completed_at` | datetime | |
| `evidence` | text | JSON blob of stage evidence |
| `error` | text | Error message |
| `artifact_ref` | str(512) | File artifact path |
| `created_at` | datetime | |

### `sibling_finding`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pipeline_id` | FK→immunity_pipeline | |
| `candidate_location` | str(512) | File/function location |
| `similarity_reason` | text | Why it was flagged |
| `confidence` | float | |
| `verification_status` | enum(VerificationStatusEnum) | Always `potential_match` unless independently verified |
| `evidence` | text | JSON evidence |
| `created_at` | datetime | |

### `pattern_library_entry`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pattern_signature` | str(512) | e.g. `AssertionError:buggy_stats.py:accumulator_reset` |
| `description` | text | Human-readable description |
| `source_pipeline_id` | FK→immunity_pipeline (nullable) | |
| `regression_test_ref` | str(512) | Failing test path |
| `affected_area` | str(255) | Module/subsystem |
| `metadata_json` | text | JSON metadata |
| `created_at` | datetime | |

---

## Phase 7 Models

### `pipeline_state_transition`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pipeline_id` | str(64) | |
| `stage_name` | str(128) | |
| `from_state` | str(64) | |
| `to_state` | str(64) | |
| `timestamp` | datetime | |
| `reason` | text | Human-readable reason |
| `evidence_ref` | str(128) | |
| `execution_id` | str(64) | |
| `created_at` | datetime | |

### `immunity_hypothesis`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pipeline_id` | str(64) | |
| `description` | text | Hypothesis statement |
| `status` | enum(HypothesisStatusEnum) | OPEN/VERIFIED/REJECTED |
| `supporting_evidence` | text | JSON list |
| `refuting_evidence` | text | JSON list |
| `source_strategy` | str(128) | |
| `verified_by` | str(128) | |
| `created_at` | datetime | |
| `updated_at` | datetime | |

### `fix_candidate`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `pipeline_id` | str(64) | |
| `strategy_name` | str(128) | |
| `affected_file` | str(512) | |
| `diff` | text | Patch |
| `rationale` | text | |
| `status` | enum(FixCandidateStatusEnum) | PENDING/APPLIED/VERIFIED/REJECTED/ROLLED_BACK |
| `verification_evidence` | text | |
| `rejection_reason` | text | |
| `attempt_number` | int | |
| `created_at` | datetime | |
| `updated_at` | datetime | |

### `immunity_checkpoint`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `fix_candidate_id` | FK→fix_candidate | |
| `pipeline_id` | str(64) | |
| `file_path` | str(512) | |
| `original_content` | text | File content before fix |
| `created_at` | datetime | |

---

## Adaptive Evidence Models (Phase 5/6)

### `evidence_item`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `claim_id` | str(64) | |
| `strategy_name` | str(128) | |
| `evidence_type` | str(64) | |
| `result` | enum(EvidenceResultEnum) | PASS/FAIL/INSUFFICIENT/CONFLICT/ERROR |
| `confidence` | float | |
| `command` | str(1024) | |
| `raw_output` | text | |
| `file_ref` | str(512) | |
| `line_ref` | int | |
| `is_independent` | bool | |
| `depends_on_evidence_id` | str(64) | |
| `created_at` | datetime | |

### `review_claim`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `claim_type` | str(64) | code_correctness/test_coverage/documentation |
| `claim_text` | text | |
| `status` | enum(ClaimStatusEnum) | OPEN/SUPPORTED/REFUTED/INSUFFICIENT/CONFLICTED |
| `verdict_contribution` | enum(VerdictContributionEnum) | NONE/ADVISORY/AUTHORITATIVE |
| `created_at` | datetime | |

### `evidence_gap`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `claim_id` | str(64) | |
| `gap_type` | enum(EvidenceGapTypeEnum) | MISSING/CONFLICTING/STALE/FAILED_STRATEGY |
| `description` | text | |
| `suggested_strategy` | str(128) | |
| `resolved` | bool | |
| `created_at` | datetime | |

### `strategy_trace_entry`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `step_number` | int | |
| `claim_id` | str(64) | |
| `strategy_name` | str(128) | |
| `selection_reason` | text | Why this strategy was selected |
| `prerequisites_met` | bool | |
| `execution_result` | str(32) | PASS/FAIL/INSUFFICIENT/ERROR |
| `evidence_item_id` | str(64) | |
| `remaining_gap` | text | |
| `next_decision` | str(64) | |
| `stopping_reason` | str(128) | |
| `started_at` | datetime | |
| `completed_at` | datetime | |

---

## Phase 6 Advanced Models

### `advanced_strategy_execution`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `strategy_name` | str(128) | |
| `result` | enum(AdvancedStrategyResultEnum) | PASS/FAIL/INSUFFICIENT/ERROR/SKIPPED |
| `confidence` | float | |
| `seed` | int | Deterministic seed used |
| `iterations_used` | int | |
| `elapsed_ms` | int | |
| `raw_output` | text | |
| `evidence_json` | text | |
| `cleanup_completed` | bool | |
| `created_at` | datetime | |

### `advanced_evidence_item`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `execution_id` | FK→advanced_strategy_execution | |
| `review_run_id` | FK→review_run | |
| `evidence_type` | str(64) | |
| `location` | str(512) | |
| `description` | text | |
| `payload_json` | text | |
| `seed` | int | |
| `created_at` | datetime | |

### `counterexample_record`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `strategy_name` | str(128) | |
| `property_description` | text | |
| `original_input_repr` | text | |
| `minimized_input_repr` | text | |
| `failure_reason` | text | |
| `seed` | int | |
| `is_minimized` | bool | |
| `created_at` | datetime | |

### `mutation_summary`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `total_mutants` | int | |
| `killed` | int | |
| `survived` | int | |
| `invalid` | int | |
| `kill_rate` | float | killed / total_mutants |
| `seed` | int | |
| `surviving_locations` | text | JSON list |
| `created_at` | datetime | |

### `fault_localization_result`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `review_run_id` | FK→review_run | |
| `n_failing` | int | |
| `n_passing` | int | |
| `ranking_json` | text | JSON sorted ranking |
| `top_suspect` | str(512) | Highest-ranked location |
| `top_score` | float | Ochiai score of top suspect |
| `created_at` | datetime | |

---

## Replay Models

### `replay_case`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `label` | str(255) | Human-readable case name |
| `description` | text | |
| `repository_path` | str(512) | |
| `included_files` | text | JSON list of relative paths |
| `ground_truth` | enum(GroundTruthEnum) | BUG/SAFE/AMBIGUOUS |
| `ground_truth_source` | enum(ReplayAgentEnum) | HUMAN/BOB_BUILTIN/RECEIPTS/NOT_AVAILABLE |
| `ground_truth_notes` | text | |
| `is_valid` | bool | |
| `validation_error` | text | |
| `created_at` | datetime | |

### `replay_result`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `replay_case_id` | FK→replay_case | |
| `verdict` | enum(VerdictEnum) | |
| `correct` | bool | |
| `caught_bug` | bool | |
| `false_alarm` | bool | |
| `missed_bug` | bool | |
| `escalated` | bool | |
| `execution_failed` | bool | |
| `elapsed_ms` | int | |
| `review_run_id` | FK→review_run (nullable) | |
| `output` | text | |
| `error` | text | |
| `planner_trace_json` | text | JSON strategy trace (Phase 8) |
| `strategies_used` | str(1024) | Comma-separated strategy names (Phase 8) |
| `strategy_count` | int | Total steps executed (Phase 8) |
| `created_at` | datetime | |

### `replay_run`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `label` | str(255) | |
| `status` | enum(ReplayCaseStatusEnum) | pending/running/completed/failed/invalid |
| `metrics_json` | text | JSON aggregate metrics |
| `total_cases` | int | |
| `cases_run` | int | |
| `cases_failed` | int | |
| `started_at` | datetime | |
| `completed_at` | datetime | |
| `created_at` | datetime | |

---

## Key Enumerations

| Enum | Values |
|------|--------|
| `VerdictEnum` | SAFE, BUG_DETECTED, ESCALATE |
| `ReviewStatusEnum` | pending, running, completed, failed |
| `AgentStatusEnum` | pending, running, completed, error, timeout, insufficient_evidence |
| `AgentTypeEnum` | test_runner, catching_test, documentation_check, history_check |
| `SeverityEnum` | PASS, INFO, LOW, MEDIUM, HIGH, CRITICAL |
| `RiskLevelEnum` | low, medium, high, critical |
| `ImmunityStatusEnum` | pending, running, passed, failed, blocked, escalated |
| `StageTypeEnum` | reproduce, root_cause, fix, verify, regression_test, sibling_hunt, documentation, pattern |
| `PipelineStateEnum` | PENDING, RUNNING, REPRODUCING, ROOT_CAUSE, FIXING, VERIFYING, REGRESSION_TESTING, SIBLING_HUNT, DOCUMENTING, PATTERN_EVALUATION, IMMUNITY_COMPLETE, BLOCKED, ESCALATED, FAILED |
| `HypothesisStatusEnum` | OPEN, VERIFIED, REJECTED |
| `FixCandidateStatusEnum` | PENDING, APPLIED, VERIFIED, REJECTED, ROLLED_BACK |
| `EvidenceResultEnum` | PASS, FAIL, INSUFFICIENT, CONFLICT, ERROR |
| `ClaimStatusEnum` | OPEN, SUPPORTED, REFUTED, INSUFFICIENT, CONFLICTED |
| `VerdictContributionEnum` | NONE, ADVISORY, AUTHORITATIVE |
| `EvidenceGapTypeEnum` | MISSING, CONFLICTING, STALE, FAILED_STRATEGY |
| `GroundTruthEnum` | BUG, SAFE, AMBIGUOUS |
| `AdvancedStrategyResultEnum` | PASS, FAIL, INSUFFICIENT, ERROR, SKIPPED |
