# MindWell: Project Context, LLMOps Roadmap, and Interview Learning Guide

## 1. Purpose of This Document

This document is the central technical and learning reference for the MindWell project. It describes:

- what MindWell currently does;
- the known application and agent architecture;
- the parts that must still be verified from the repository;
- the limitations of the current implementation;
- the LLMOps, MLOps, CI/CD, evaluation, optimization, and deployment capabilities to be added;
- how each technique will solve a specific MindWell problem;
- the experiments and evidence required to demonstrate improvement; and
- the knowledge that should be developed for technical interviews.

This is not a short deadline-based plan. The objective is to implement each capability carefully enough to understand, measure, explain, and defend the technical choices during an interview.

This file should be read by Codex or any developer before changing the project. Items labelled **To verify** are not confirmed facts and must be checked against the repository.

---

## 2. Project Overview

MindWell is an AI-powered mental-wellbeing platform that uses an agentic workflow to provide conversational wellbeing support. It combines onboarding information, conversation history, user memory, retrieval-augmented generation (RAG), safety assessment, and a coaching agent.

The platform is intended to:

- provide supportive and context-aware wellbeing conversations;
- personalize responses using relevant user information;
- ground appropriate responses in a curated knowledge base;
- identify potentially risky conversations and route them safely;
- avoid unnecessary use of agents, memory, or RAG;
- make every important AI decision observable and evaluable; and
- provide a practical implementation of agentic AI, LLMOps, and MLOps principles.

MindWell is a wellbeing-support system. It must not be represented as a replacement for a licensed mental-health professional, emergency service, diagnosis, or clinical treatment.

---

## 3. Project Goals

### 3.1 User and product goals

- Deliver relevant, empathetic, clear, and actionable responses.
- Maintain conversational continuity without overusing personal history.
- Use external knowledge only when it improves the response.
- Detect safety concerns with high recall, particularly for high-risk cases.
- Provide predictable fallback behaviour when a service fails.
- Reduce response latency without sacrificing safety or quality.

### 3.2 Engineering goals

- Make the application reproducible across development environments.
- Decouple agent logic from a specific LLM provider or serving framework.
- Version code, prompts, models, RAG settings, memory policies, and evaluation data.
- Trace and evaluate every important component of the agent workflow.
- Build automated tests and CI/CD quality gates.
- Package the application using Docker.
- Deploy a controlled staging/demo environment.
- Establish measurable rollback and continuous-improvement processes.

### 3.3 Learning and interview goals

- Learn Git and GitHub through real project work.
- Understand agentic orchestration and conditional routing.
- Implement LangSmith tracing, evaluation, and monitoring.
- Compare open-weight models and inference approaches.
- Learn RAG, memory, prompt, and latency optimization.
- Implement experiment tracking and a model/configuration registry.
- Implement automated testing, CI/CD, and containerization.
- Explain design decisions using hypotheses, experiments, metrics, results, and trade-offs.

---

## 4. Known Current MindWell Architecture

The currently understood workflow is:

```text
User message
    |
    v
Safety Agent
    |
    v
Orchestrator Agent
    |
    +--> Memory Agent, when personalization/history is needed
    |
    +--> RAG, when external grounded knowledge is needed
    |
    v
Coach Agent
    |
    v
Final response
    |
    v
Conversation, analysis, and memory storage
```

### 4.1 Safety Agent

Expected responsibility:

- examine the user request for safety concerns;
- classify or score risk;
- determine whether normal processing, a safer response, or an escalation path is required; and
- prevent downstream coaching behaviour from overriding critical safety handling.

**To verify:** model/rules used, risk labels, thresholds, prompt, structured output, fallbacks, and whether it runs for every request.

### 4.2 Orchestrator Agent

Expected responsibility:

- determine which components are necessary for a request;
- decide whether to use memory, RAG, both, or neither;
- preserve workflow state; and
- pass the appropriate context to the Coach Agent.

**To verify:** whether routing is rule-based, LLM-based, or hybrid; the graph structure; routing schema; retry logic; and current failure handling.

### 4.3 Memory Agent

Expected responsibility:

- retrieve relevant information from the current conversation or stored user memory;
- avoid injecting unrelated personal information; and
- provide compact context for personalization.

**To verify:** memory types, retrieval method, scoring, write policy, summarization, retention, deduplication, and database queries.

### 4.4 RAG pipeline

Expected responsibility:

- retrieve relevant information from a curated wellbeing knowledge base;
- provide supporting context to the Coach Agent; and
- help generate grounded responses.

Known RAG-related fields include:

- `rag_used`
- `rag_source`
- `retrieved_count`
- `retrieval_score`
- `grounded_flag`
- `rag_benefit_flag`

**To verify:** document sources, ingestion, chunking, embedding model, vector store, similarity metric, retrieval `k`, filters, reranking, prompt construction, and grounding method.

### 4.5 Coach Agent

Expected responsibility:

- combine the request, safe instructions, relevant memory, and retrieved knowledge;
- generate a supportive and context-appropriate response; and
- follow safety, tone, and scope restrictions.

**To verify:** current model, provider, prompt, generation parameters, streaming, output validation, and fallback behaviour.

---

## 5. Known Current Technology Stack

| Layer | Current or expected technology | Purpose | Verification status |
|---|---|---|---|
| User interface | Streamlit | Web interface | Known |
| Agent orchestration | LangChain/LangGraph | Multi-step agent workflow | Known; details to verify |
| Local inference | Ollama | Local model serving | Known; exact models to verify |
| Database | Neon/PostgreSQL or current configured database | Persistent application data | To verify |
| RAG | Existing retrieval pipeline | Grounded knowledge retrieval | Details to verify |
| Source control | Git and GitHub | Version control and collaboration | Repository exists |
| Development | VS Code and Codex | Development, explanation, testing, and debugging | Planned workflow |
| Observability | Application logs/current metadata | Debugging and analysis | To verify |
| Deployment | Local execution | Current runtime | To verify |

Important terminology: Ollama is a model-serving runtime, not an LLM itself. Open-weight models such as Llama, Mistral, Qwen, Gemma, or Phi may be served through Ollama or other inference frameworks.

---

## 6. Known Data and Database Context

Known or previously discussed tables include:

- `users`
- `onboarding_que`
- `chat_messages`
- `chat_analysis`
- `user_memory`

The application includes a 12-question onboarding flow.

### 6.1 LLMOps metadata to add or standardize

Where appropriate, record:

- trace and run identifiers;
- session and anonymized user identifiers;
- timestamp and environment;
- workflow/graph version;
- selected route and invoked agents;
- safety result and confidence;
- model provider, model name, and model version;
- prompt names and versions;
- generation parameters;
- memory types requested and returned;
- RAG configuration and knowledge-base version;
- retrieved document identifiers and scores;
- prompt, completion, and total tokens;
- safety, routing, retrieval, and generation latency;
- total end-to-end latency;
- error, retry, timeout, and fallback information; and
- offline/online evaluation and user-feedback results.

Sensitive text should not automatically be copied into traces. Redaction, consent, access, and retention rules must be established before real user data is observed externally.

---

## 7. Current Limitations and Questions to Verify

The repository inspection should determine whether these suspected limitations are present:

- local Ollama dependency prevents direct cloud deployment;
- high end-to-end response latency;
- every agent may run even when it is unnecessary;
- memory and RAG may be retrieved without sufficient routing logic;
- multiple independent tasks may be executed sequentially instead of concurrently;
- prompt and context length may be larger than necessary;
- model clients, database clients, or indexes may be inefficient;
- dependency versions may not be fully pinned;
- prompts and configurations may not be versioned;
- automated unit, integration, safety, and regression tests may be incomplete;
- evaluation datasets and baselines may not exist;
- experiment tracking and promotion/rollback rules may be missing;
- CI/CD and Docker may not yet be configured; and
- production-grade privacy, monitoring, and incident procedures may be incomplete.

These must be measured and verified. They must not be treated as facts merely because they appear in this roadmap.

---

## 8. Baseline Measurement Before Optimization

Optimization must start with a repeatable baseline. Use a versioned evaluation dataset and record at least:

### 8.1 Performance metrics

- end-to-end P50, P95, and P99 latency;
- latency for safety, routing, memory, RAG, generation, and database operations;
- time to first token and total generation time;
- number of LLM calls per request;
- prompt, completion, and total tokens;
- error, retry, timeout, and fallback rates;
- requests per minute and concurrency, where meaningful; and
- CPU, GPU, RAM, and model-loading behaviour for local inference.

### 8.2 Quality and safety metrics

- high-risk recall and false-negative count;
- risk-classification precision, recall, and F1;
- routing accuracy;
- unnecessary-agent invocation rate;
- memory relevance and appropriateness;
- retrieval Hit Rate, Recall@K, Precision@K, MRR, and NDCG;
- context relevance and groundedness;
- response correctness, relevance, empathy, clarity, and helpfulness;
- hallucination or unsupported-claim rate; and
- response consistency and human-review outcomes.

### 8.3 Baseline artifacts

Preserve:

- Git commit/tag;
- dependency lock or pinned requirements;
- prompts and configuration versions;
- dataset version;
- experiment record;
- raw and summarized metrics; and
- known failure examples.

---

## 9. Git and GitHub Workflow

Git will be used for local version control. GitHub will be the remote source of truth and the integration point for Pull Requests, CI/CD, releases, and deployment.

Suggested branches:

```text
main                       Stable/releasable code
develop                    Integrated development
feature/langsmith          Tracing and evaluation
feature/model-providers    Provider abstraction
feature/agent-routing      Conditional routing
feature/memory-routing     Memory optimization
feature/rag-optimization   Retrieval experiments
feature/latency            Performance work
feature/testing            Automated tests
feature/cicd               GitHub Actions
feature/docker             Containerization
```

Normal workflow:

```text
Issue or experiment hypothesis
    -> feature branch
    -> focused implementation
    -> local tests and evaluation
    -> commit and push
    -> Pull Request
    -> automated quality gates
    -> review and merge
    -> tag/release when appropriate
```

Learning goals include cloning, status, diff, add, commit, push, pull, branching, merging, rebasing where appropriate, conflict resolution, Pull Requests, tags, releases, rollback, `.gitignore`, GitHub Issues, and branch protection.

---

## 10. Model-Provider Abstraction and Open-Weight Models

Agent logic should depend on a common LLM interface, not directly on Ollama or one API.

```text
MindWell agents
      |
      v
Common LLM provider interface
      |
      +--> Ollama (local convenience)
      +--> Hugging Face Transformers (direct local inference)
      +--> vLLM (optimized model serving)
      +--> hosted endpoint serving an open-weight model
      +--> optional proprietary provider for comparison/fallback
```

Configuration should select the provider, for example:

```text
LLM_PROVIDER=ollama
COACH_MODEL=<model-name>
ROUTER_MODEL=<model-name>
```

Model families to consider experimentally include Llama, Mistral, Qwen, Gemma, Phi, and suitable task-specific models. The actual candidates must be selected according to license, hardware, context length, language coverage, quality, safety behaviour, latency, and deployment constraints.

### 10.1 Model comparison criteria

- instruction following;
- safety behaviour;
- response quality and empathy;
- groundedness;
- context-window requirements;
- time to first token and total latency;
- throughput and concurrency;
- CPU/GPU/RAM needs;
- quantization options;
- licensing and deployment restrictions;
- operational complexity; and
- cost for hosted inference.

The best architecture may use different models for different tasks: a small fast model or deterministic classifier for routing, and a stronger model for coaching.

---

## 11. LangSmith Observability and Evaluation

LangSmith will be used as the primary LLM-specific observability and evaluation layer for the LangChain/LangGraph workflow.

Expected trace structure:

```text
MindWell request
|-- Safety classification
|-- Orchestrator decision
|-- Memory retrieval (conditional)
|-- RAG retrieval/reranking (conditional)
`-- Coach generation
```

### 11.1 Trace information

- anonymized/session identifiers;
- environment and code version;
- graph and prompt versions;
- model and provider;
- inputs/outputs after approved redaction;
- route and invoked components;
- retrieved items and scores;
- tokens and latency;
- errors, retries, and fallbacks;
- evaluation scores; and
- user or reviewer feedback.

### 11.2 LangSmith use cases

- compare prompt, model, RAG, and memory configurations;
- debug slow requests and incorrect routing;
- build versioned evaluation datasets from reviewed examples;
- run offline evaluations before promotion;
- sample controlled online traces in staging;
- convert failures into regression examples; and
- link a result to the exact code and configuration version.

LangSmith must be configured with privacy controls. Identifiable mental-health conversations should not be exported without an approved consent, redaction, retention, and access-control design.

---

## 12. Agent-Utilization and Routing Optimization

Every request should pass through the minimum safe and useful workflow.

```text
User request
    |
    v
Mandatory/appropriate safety handling
    |
    v
Routing decision
    |-- simple supportive request ------> Coach
    |-- personal-history dependent -----> Memory + Coach
    |-- knowledge dependent ------------> RAG + Coach
    `-- both dependent -----------------> Memory + RAG + Coach
```

Questions to test:

- Must safety use a full LLM call for every input, or can a reliable hybrid cascade be used?
- Can deterministic rules safely handle obvious cases while uncertain cases use a classifier/LLM?
- Can a smaller model perform orchestration accurately?
- Which requests genuinely require RAG?
- Which requests genuinely require short-term or long-term memory?
- Can independent memory and RAG retrieval run concurrently?
- Can repeated safe computations be cached?
- Can structured router output prevent invalid transitions?
- What are the safe timeout and fallback routes?

Metrics:

- routing accuracy;
- average agents invoked per request;
- unnecessary-agent rate;
- missed-required-agent rate;
- tokens and cost per request;
- P50/P95/P99 latency;
- safety and response-quality change; and
- error/fallback rates.

No latency optimization may bypass required safety behaviour.

---

## 13. Memory Architecture and Optimization

Memory should be separated by function.

### 13.1 Short-term conversational memory

- recent turns within the current session;
- used for immediate continuity;
- bounded by messages or tokens; and
- summarized when the conversation becomes long.

### 13.2 Long-term semantic user memory

- stable, useful facts or preferences;
- stored selectively rather than copying every message;
- retrieved only when relevant; and
- subject to consent, correction, retention, and deletion policies.

### 13.3 Episodic memory

- important previous interactions or events;
- ranked using relevance, recency, and importance; and
- used when a current request depends on a prior event.

### 13.4 Knowledge memory (RAG)

- curated external wellbeing information;
- distinct from personal memory; and
- retrieved to ground knowledge-dependent answers.

### 13.5 Memory routing

```text
Depends on recent dialogue?        -> short-term memory
Depends on a prior personal fact?  -> long-term/episodic memory
Needs external trusted knowledge?  -> RAG
Needs none of these?               -> direct Coach path
```

Optimization experiments:

- top-K tuning;
- relevance thresholds;
- recency and importance weighting;
- hybrid structured/vector retrieval;
- memory summarization;
- context compression;
- deduplication;
- selective write policies;
- retention/expiration policies;
- token-budget allocation; and
- detection of inappropriate or irrelevant personalization.

---

## 14. RAG Optimization

The complete RAG lifecycle should be versioned and evaluated:

```text
Source validation
-> cleaning
-> chunking
-> embedding
-> indexing
-> query processing
-> retrieval
-> reranking/filtering
-> context construction
-> response generation
-> groundedness evaluation
```

Experiments should compare:

- fixed-size, recursive, and semantic chunking;
- chunk size and overlap;
- embedding models;
- cosine/dot/other supported similarity approaches;
- dense versus hybrid retrieval;
- metadata filtering;
- retrieval `k`;
- relevance thresholds;
- query rewriting or decomposition;
- cross-encoder/LLM reranking;
- contextual compression; and
- RAG enabled versus bypassed.

Metrics include Hit Rate, Recall@K, Precision@K, MRR, NDCG, context relevance, groundedness, answer correctness, latency, and measured RAG benefit.

---

## 15. Response-Quality Improvement

Response quality will be improved through controlled experiments rather than subjective prompt editing.

Experiment dimensions:

- system and agent prompts;
- prompt structure and few-shot examples;
- model and generation settings;
- retrieved knowledge;
- selected personal memory;
- response length and organization;
- empathy and non-judgmental tone;
- actionable but appropriately scoped suggestions;
- uncertainty and source-grounding behaviour;
- repetition control; and
- safety-specific response templates and escalation rules.

Evaluation dimensions:

- safety;
- relevance;
- correctness;
- groundedness;
- empathy;
- clarity;
- helpfulness;
- actionability;
- appropriate personalization;
- absence of unsupported diagnosis or claims; and
- human reviewer preference.

Automated LLM-as-judge evaluation may support iteration, but safety-critical behaviour requires human-reviewed expectations and regression tests.

---

## 16. Latency Profiling and Optimization

Treat total latency as a composition of measurable stages:

```text
Total latency =
  safety
  + routing
  + memory
  + RAG/reranking
  + generation
  + database/network
  + framework overhead
```

Potential improvements:

- eliminate unnecessary LLM and agent calls;
- use smaller/faster models for classification and routing;
- run independent memory and RAG operations concurrently;
- cache embeddings and safe reusable retrieval results;
- reuse initialized LLM, database, and HTTP clients;
- reduce prompts and retrieved context while preserving quality;
- summarize older history;
- apply retrieval thresholds and context budgets;
- optimize database queries and indexes;
- use asynchronous I/O where appropriate;
- stream tokens to reduce perceived latency;
- add deadlines, timeouts, retries with backoff, and fallbacks;
- preload/warm local models;
- evaluate quantization;
- use vLLM features such as efficient serving/batching when suitable;
- move non-critical analytics writes off the response-critical path; and
- select models using a quality-latency-cost Pareto analysis.

For each optimization, compare the same evaluation dataset before and after. Report P50, P95, and P99, not only the mean. Reject an optimization if it materially harms safety or response quality.

---

## 17. Evaluation Framework

### 17.1 Evaluation datasets

Create reviewed, versioned datasets for:

- normal wellbeing conversation;
- medium-risk input;
- high-risk input;
- ambiguous and adversarial input;
- prompt injection attempts;
- knowledge/RAG questions;
- memory-dependent questions;
- requests that must not use personal memory;
- requests that need neither RAG nor memory;
- routing decisions;
- multi-turn continuity;
- model comparison; and
- latency/concurrency benchmarking.

### 17.2 Component evaluation

- Safety: risk recall, precision, false negatives, escalation behaviour.
- Router: correct route, unnecessary and missed agents.
- Memory: relevance, faithfulness to stored facts, privacy, usefulness.
- Retrieval: Hit Rate, Recall@K, Precision@K, MRR, NDCG.
- Generation: safety, correctness, groundedness, relevance, empathy, clarity.

### 17.3 End-to-end evaluation

- complete route correctness;
- final response quality and safety;
- latency and reliability;
- consistency across repeated runs; and
- human preference or rubric score.

### 17.4 Offline and online evaluation

- Offline evaluation occurs before a configuration is promoted.
- Online evaluation occurs only in an approved environment with appropriate data controls.
- Production or staging failures should be reviewed and added to the offline regression set.

---

## 18. Experiment Tracking

Every meaningful experiment should record:

```text
Experiment ID and date
Hypothesis
Code commit
Dataset version
Model/provider and generation settings
Prompt versions
Router, memory, and RAG configuration
Baseline metrics
Candidate metrics
Latency/resource results
Qualitative failure analysis
Conclusion and promotion decision
```

Example experiments:

- Does semantic chunking improve groundedness without unacceptable latency?
- Can a smaller router model reduce P95 latency while preserving routing accuracy?
- Does memory summarization reduce tokens while preserving personalization?
- Does concurrent memory/RAG retrieval reduce latency?
- Does reranking improve MRR and final-answer correctness?
- Which open-weight model provides the best quality-latency trade-off for coaching?

LangSmith will cover LLM traces and evaluations. MLflow or a lightweight versioned experiment store may be introduced to learn broader experiment tracking and registry concepts. Git commits/tags must connect experiments to code.

---

## 19. Model and Configuration Registry

MindWell requires a registry broader than model weights. A release configuration may include:

- provider and model identifier;
- quantization and serving framework;
- generation parameters;
- Safety, Router, Memory, and Coach prompt versions;
- graph/workflow version;
- safety thresholds and fallback rules;
- memory retrieval and write policies;
- embedding model and vector-index version;
- RAG chunking, retrieval, and reranking settings;
- knowledge-base version;
- evaluation dataset version; and
- required quality, safety, and latency results.

Lifecycle:

```text
Candidate -> Evaluated -> Approved for staging -> Production candidate -> Deprecated
```

The registry must support traceability, promotion, comparison, and rollback.

---

## 20. Automated Testing Strategy

### 20.1 Software tests

- unit tests for routing, database, configuration, formatting, and utilities;
- provider-contract tests so providers return a consistent schema;
- integration tests for agent paths;
- database and migration tests;
- error, retry, timeout, and fallback tests;
- Docker and deployment smoke tests; and
- security checks for committed secrets and unsafe configuration.

### 20.2 AI behavioural evaluations

- safety regression;
- route correctness;
- memory selection and non-selection;
- RAG retrieval and grounding;
- response-quality rubrics;
- prompt/model regression; and
- latency thresholds.

Key distinction:

```text
Software testing: Does the implementation function correctly?
LLM evaluation: Does the probabilistic AI behaviour meet expectations?
```

---

## 21. CI/CD Pipeline

CI/CD means Continuous Integration and Continuous Delivery/Deployment.

Proposed Pull Request pipeline:

```text
Push/Pull Request
-> formatting/linting and secret scanning
-> unit tests
-> integration tests with mocks/test services
-> safety and routing regression
-> selected LLM/RAG evaluations
-> Docker build
-> quality-gate decision
```

Proposed release pipeline:

```text
Approved merge/tag
-> build versioned artifact/image
-> store/publish artifact
-> deploy to staging
-> smoke and controlled evaluation tests
-> manual approval
-> promote or rollback
```

Start with Continuous Delivery: deployment is prepared automatically but promotion requires approval. Full Continuous Deployment may be introduced only when quality gates and rollback are reliable.

GitHub Actions should be used to learn workflow triggers, jobs, runners, dependency caching, artifacts, secrets, environments, approvals, and status checks.

---

## 22. Containerization

Docker work should include:

- `Dockerfile`;
- `.dockerignore`;
- pinned dependencies;
- non-root execution where practical;
- environment-driven configuration;
- health checks;
- deterministic startup command;
- local build and run verification;
- image naming and version tags;
- vulnerability/dependency scanning; and
- container-registry and promotion concepts.

Secrets and user data must not be baked into the image.

---

## 23. Deployment Architecture

### 23.1 Local development

```text
VS Code + Codex
    -> Streamlit MindWell
    -> Ollama/Transformers/vLLM as appropriate
    -> development database/vector store
    -> LangSmith development project with safe test data
```

### 23.2 Staging/demo deployment

```text
GitHub
    -> Streamlit Community Cloud frontend/application
    -> remotely reachable hosted model endpoint
    -> staging database/vector store
    -> LangSmith staging project
```

Streamlit Community Cloud can be used for an initial controlled demo/staging application. It deploys from the GitHub repository. It does not make the Ollama service on a laptop reachable. A hosted model endpoint is therefore required for cloud staging.

The Docker image demonstrates reproducibility and supports other hosting platforms, but the initial Streamlit Community Cloud deployment may deploy directly from repository files instead of using that Docker image.

### 23.3 Future production architecture

```text
Web frontend
    -> authenticated backend API
    -> LangGraph/agent service
    -> dedicated model-serving endpoints
    -> database and vector store
    -> tracing, metrics, logs, alerts, and audit system
```

A production system may separate the UI, API, agent workflow, model server, data stores, and observability services. Hosting decisions must consider privacy, residency, availability, security, scalability, and cost.

---

## 24. Environment and Secrets Management

Separate:

- local development;
- automated testing;
- staging/demo; and
- future production.

Recommended configuration locations:

- `.env.example`: variable names and safe examples only;
- local `.env`: local secrets, excluded from Git;
- Streamlit Secrets: staging application credentials;
- GitHub Actions Secrets/Environments: CI/CD credentials and approvals; and
- production secret manager: future production credentials.

Never commit API keys, database passwords, LangSmith keys, private documents, identifiable conversations, or production data.

---

## 25. Security, Privacy, Safety, and Responsible AI

This project handles potentially sensitive mental-wellbeing information. The roadmap must include:

- consent and transparent data use;
- PII and sensitive-text redaction;
- trace and log minimization;
- retention and deletion policies;
- access control and least privilege;
- encryption in transit and at rest;
- audit logs;
- secrets management;
- prompt-injection and data-exfiltration testing;
- trusted RAG-source governance;
- safe failure and fallback responses;
- human escalation design;
- crisis-support limitations;
- explicit non-clinical scope; and
- clinical/safety expert review before real-user production use.

Safety decisions should prioritize false-negative reduction for high-risk cases while monitoring false positives and user experience.

---

## 26. Implementation and Learning Roadmap

The work is organized by knowledge and engineering maturity, not by a fixed number of days.

### Phase 1: Reproduce and understand the baseline

- Clone the repository and create an isolated environment.
- Run the complete current workflow.
- Map files, dependencies, agents, prompts, data flows, and external services.
- Measure baseline behaviour and latency.
- Pin dependencies and tag the baseline.

**Evidence:** architecture map, setup instructions, baseline tag, initial metrics, known-issue list.

### Phase 2: Establish Git/GitHub engineering workflow

- Implement branches, Pull Requests, Issues, reviews, tags, releases, and rollback.
- Protect secrets with `.gitignore` and scanning.

**Evidence:** clean commit history, PRs, tagged releases, resolved conflict example if encountered.

### Phase 3: Add LangSmith observability

- Trace the complete graph and component runs.
- Add safe metadata, versions, latency, tokens, and errors.
- Configure separate development/staging projects.

**Evidence:** trace examples, latency breakdown, identified failure/slow path.

### Phase 4: Build the evaluation framework

- Create versioned safety, routing, memory, RAG, response, and latency datasets.
- Define deterministic metrics and human rubrics.
- Establish baseline scores.

**Evidence:** evaluation datasets, scripts, reports, human-reviewed examples.

### Phase 5: Add multi-provider and open-weight model support

- Create a common provider interface.
- Support Ollama plus selected alternative serving methods.
- Compare candidate models on the same datasets.

**Evidence:** provider contract, comparison experiment, documented trade-off and selection.

### Phase 6: Optimize agent routing

- Add conditional, structured routing.
- Use smaller/deterministic approaches where safe.
- Remove unnecessary calls and parallelize independent work.

**Evidence:** before/after routing accuracy, calls/request, token usage, latency, and safety results.

### Phase 7: Optimize memory

- Separate memory types.
- Introduce selective read/write policies, relevance thresholds, summarization, and context budgets.
- Test inappropriate memory use as well as missed memory.

**Evidence:** memory evaluation set, relevance results, token/latency improvements, failure analysis.

### Phase 8: Optimize RAG

- Experiment with chunking, embeddings, retrieval, filters, reranking, and compression.
- Measure retrieval and final-answer impact.

**Evidence:** retrieval metrics, groundedness, latency, RAG-benefit experiments.

### Phase 9: Improve response quality

- Run prompt/model/context experiments.
- Use automated and human evaluation.
- Protect safety and avoid over-personalization.

**Evidence:** rubric scores, preference results, prompt versions, reviewed examples.

### Phase 10: Optimize latency and reliability

- Profile critical paths.
- Implement concurrency, caching, model right-sizing, client reuse, database optimization, streaming, and fallbacks as supported by evidence.

**Evidence:** P50/P95/P99 before/after, quality/safety non-regression, resource utilization.

### Phase 11: Add experiment tracking and registry

- Standardize experiment records.
- Link code, data, prompts, models, configurations, and results.
- Implement candidate, evaluated, approved, and deprecated states.

**Evidence:** searchable experiment history, approved release configuration, rollback record.

### Phase 12: Automate tests and CI/CD

- Add unit, integration, safety, RAG, and smoke tests.
- Add GitHub Actions and quality gates.
- Produce versioned artifacts and controlled staging deployments.

**Evidence:** passing workflow, intentionally caught regression, deployment/rollback procedure.

### Phase 13: Containerize and deploy staging

- Build and verify Docker.
- Configure Streamlit staging with a hosted model endpoint and test services.
- Verify observability and smoke tests.

**Evidence:** image build, run instructions, staging URL/status, release tag, deployment report.

### Phase 14: Monitor and improve continuously

- Review traces, failures, feedback, drift, quality, safety, and latency.
- Convert reviewed failures into regression cases.
- repeat experiments and controlled promotion.

**Evidence:** monitoring dashboard/report, incident examples, updated evaluation dataset, improvement release.

---

## 27. Continuous Improvement Loop

```text
Observe traces and metrics
    -> identify a failure or bottleneck
    -> add/review an evaluation example
    -> form a hypothesis
    -> change one controlled variable
    -> run offline tests and evaluations
    -> compare quality, safety, latency, and cost
    -> approve or reject the candidate
    -> deploy to staging
    -> monitor and repeat
```

This loop is the core mental model for LLMOps in MindWell.

---

## 28. Interview Knowledge Map

| Interview area | MindWell implementation evidence |
|---|---|
| Agentic AI | Safety, Orchestrator, Memory, RAG, and Coach workflow |
| Agent optimization | Conditional routing, structured decisions, parallel execution, smaller models |
| LLMOps | LangSmith tracing, datasets, evaluation, monitoring, regression loop |
| MLOps | Experiment tracking, registry, promotion, rollback, CI/CD, Docker |
| Open-weight models | Llama/Mistral/Qwen/Gemma/Phi comparison through provider abstraction |
| RAG | Chunking, embeddings, filtering, reranking, metrics, groundedness |
| Memory | Short-term, long-term, episodic, semantic, and selective retrieval |
| Latency | Profiling, concurrency, caching, streaming, model right-sizing, P95/P99 |
| Evaluation | Offline/online, deterministic metrics, LLM judge, human review |
| CI/CD | GitHub Actions, tests, evaluation gates, artifact, staging, rollback |
| Responsible AI | Safety routing, privacy, redaction, escalation, auditability |
| Deployment | Local, Streamlit staging, containerized/future service architecture |

For every topic, be able to explain:

1. the original problem;
2. the baseline and evidence;
3. the hypothesis;
4. the implementation;
5. the metrics and experiment;
6. the result;
7. failure cases and trade-offs; and
8. the next improvement.

---

## 29. Definition of Maturity

- **Level 1 — Reproducible:** fresh clone runs with documented dependencies and configuration.
- **Level 2 — Observable:** component traces, versions, errors, tokens, and latency are visible.
- **Level 3 — Evaluable:** versioned datasets and regression evaluations exist.
- **Level 4 — Optimized:** routing, memory, RAG, response quality, and latency are measurably improved.
- **Level 5 — Governed:** experiments, configurations, promotion, and rollback are controlled.
- **Level 6 — Automated:** tests, CI/CD, Docker builds, and staging checks run reliably.
- **Level 7 — Monitored:** staging behaviour feeds a continuous improvement loop.
- **Level 8 — Production assessed:** privacy, security, clinical safety, availability, and operations have formal approval.

---

## 30. Instructions for Codex and Contributors

Before modifying code:

1. Read this document and the repository-specific instructions.
2. Inspect the relevant implementation and tests.
3. Clearly distinguish verified facts from assumptions.
4. Explain the problem, proposed solution, metrics, and affected files.
5. Prefer a small, reversible change tied to one hypothesis.

During implementation:

- preserve unrelated user changes;
- never expose or commit secrets or sensitive data;
- do not bypass safety behaviour for speed;
- keep providers behind a consistent interface;
- add or update tests and evaluations;
- record configuration and prompt versions;
- run relevant tests, evaluations, and benchmarks; and
- use feature branches and meaningful commits.

After implementation, report:

- files changed;
- conceptual explanation;
- commands and tests executed;
- before/after results;
- risks, assumptions, and remaining limitations; and
- recommended next experiment.

---

## 31. Project Progress Checklist

### Baseline and version control

- [x] Repository cloned and verified
- [ ] Local environment reproducible — works, but only when launched from the
      project root; launching from source_code/ (as the setup docs say) was
      broken and is fixed in code, docs themselves not yet corrected
- [x] Complete current workflow tested — real browser click-through:
      signup, onboarding, login, multi-turn chat, verified against real DB rows
- [x] Architecture and dependencies documented
- [x] Baseline metrics recorded — real per-agent latency captured before/after
      the LangChain migration (see commit 3fc0310); not yet a formal P50/P95/P99
      dataset (sample sizes so far are one-off, not a repeatable benchmark run)
- [ ] Baseline Git tag created
- [ ] Branch and Pull Request workflow established — feature branches and
      real commit messages are in use (see git log); no PR/remote workflow yet

### Observability and evaluation

- [x] LangSmith development tracing integrated — opt-in, fail-open
      (tracing.py), custom trace() spans around each agent call
      (engine.py::_call_agent), verified against the real account with
      synthetic data only
- [x] Privacy/redaction policy defined for traces — narrower than a full
      consent/retention policy (that's still open, see below), but the
      concrete leak-prevention mechanism is done: a real leak was found
      (LangChain's own ChatOllama/LangGraph auto-tracing bypassed the
      custom span and uploaded full raw prompts/messages), root-caused to
      three independent default-client resolution paths, and fixed by
      installing one Client(hide_inputs=True, hide_outputs=True) across
      all three (tracing.py::_install_redacted_default_client). Verified
      by pulling real trace content back from LangSmith before and after —
      before: full system prompt + raw user message present; after: empty
      inputs/outputs on every span including LangGraph nodes and ChatOllama
      itself. Still open: real user conversations remain out of scope for
      tracing until a full consent/retention policy exists — this only
      makes the mechanism safe for if/when that happens.
- [ ] Component latency and tokens recorded
- [ ] Safety evaluation dataset created
- [ ] Routing evaluation dataset created
- [ ] Memory evaluation dataset created
- [ ] RAG evaluation dataset created
- [ ] Response-quality rubric created
- [ ] Latency benchmark created

### Models, agents, memory, and RAG

- [ ] Common model-provider interface implemented — LangChain now wired in as
      the call mechanism (llm_provider.py::_call_ollama uses ChatOllama), but
      there's still only one provider actually connected; no config-driven
      provider switch exists yet
- [x] Ollama provider verified — verified through the new LangChain path
      specifically: real latency baseline, forced model-fallback test, forced
      connection-failure test, full regression suite, all passing
- [ ] At least one alternative open-weight serving path verified
- [ ] Model comparison completed
- [x] Conditional agent routing implemented — replaced the two independently
      duplicated routers (engine.py + pages.py) with one LangGraph graph
      (router_graph.py); verified equivalent to both prior implementations
      on 17 real cases plus the full crisis-hint payload before cutover
- [ ] Unnecessary-agent rate measured
- [ ] Memory types and policies documented
- [ ] Memory routing evaluated
- [ ] RAG baseline evaluated
- [ ] RAG optimization experiments completed
- [ ] Response-quality experiments completed

### Performance and reliability

- [ ] P50/P95/P99 baseline recorded
- [ ] Critical latency path identified
- [ ] Concurrency/parallel retrieval evaluated
- [ ] Caching evaluated safely
- [ ] Context and token budgets optimized
- [ ] Database/client performance reviewed
- [ ] Streaming evaluated
- [ ] Timeouts, retries, and fallbacks tested
- [ ] Final performance report completed

### MLOps, CI/CD, and deployment

- [ ] Experiment-tracking format/tool implemented
- [ ] Model/configuration registry implemented
- [ ] Unit and integration tests implemented
- [ ] Safety and LLM regression gates implemented
- [ ] GitHub Actions CI configured
- [ ] Controlled CD/staging workflow configured
- [ ] Dockerfile and `.dockerignore` added
- [ ] Docker image builds and runs
- [ ] Secrets and environments configured
- [ ] Streamlit staging deployed
- [ ] Hosted model endpoint connected
- [ ] Staging smoke tests pass
- [ ] Rollback procedure tested

### Documentation and interview readiness

- [ ] README updated
- [ ] Architecture diagram updated
- [ ] Experiment reports available
- [ ] Deployment and rollback documented
- [ ] Security/privacy limitations documented
- [ ] Interview knowledge map reviewed
- [ ] Project case study prepared using problem, experiment, result, and trade-off

---

## 32. Living Status Log

Update this section after each milestone.

```text
Current phase: Baseline stabilization complete. LangChain provider wrapper
  complete. LangGraph routing migration complete. LangSmith tracing complete
  (development, synthetic-data-verified, redaction-fixed).
Current code version: main, commit 4e1177a (LangSmith milestone commit to follow)
Current approved configuration: Ollama via LangChain's ChatOllama; routing
  decisions via router_graph.py (LangGraph); per-agent generation settings
  unchanged from AGENT_CONFIG in llm_provider.py; tracing opt-in via
  tracing.py, active only when a LangSmith key is configured, with a
  process-wide redacting Client (hide_inputs/hide_outputs=True) installed
  across all of LangSmith's/LangChain's default-client resolution paths
Latest evaluation dataset version: none formal yet, but router_graph.py's
  17-case battery (tests/test_router_graph.py) is a real, reusable regression
  set for routing correctness specifically — includes every routing bug found
  this session
Best quality results: no formal quality rubric/scoring implemented yet;
  verification so far is real-conversation testing + targeted regression tests
Current P50/P95/P99 latency: not yet a real percentile dataset (samples too
  small). Representative single-sample timings from the LangChain migration
  baseline: greeting (no LLM call) 0.00s, coping request ~16-18s, emotional
  support ~6s, crisis-phrase classification ~7-9s. Routing/classification
  itself is pure Python (no LLM call) and effectively instant either way.
Known failures:
  - AI occasionally leaks raw template placeholder text (e.g. "[insert ... if
    any]") into real replies — a prompt instruction was added but is not
    reliably followed by this model; not yet given a deterministic guardrail
    the way the memory-fabrication issue was
  - No test/eval coverage yet for RAG retrieval quality
  - Setup docs (README, Setup_and_Run_Instructions.md) still describe an
    OpenAI/LangChain/FAISS stack that was never actually true — not yet corrected
Current deployment status: local only. Ollama-only in practice — LangChain
  makes a second provider possible to add but none is wired up yet
Next hypothesis/experiment: with tracing, routing, and provider wrapping all
  now real (not hand-rolled), the next useful step is building actual
  evaluation datasets (safety/routing/memory/RAG) on top of what LangSmith
  now captures — right now there's a verified pipe for trace data but
  nothing yet reading it for regression/quality signal. Real-conversation
  tracing stays out of scope until a consent/retention policy is designed
  (roadmap section 11).
```

---

## 33. Final Project Mental Model

```text
Git versions the work.
Tests protect deterministic behaviour.
LangSmith exposes agent behaviour.
Evaluations judge quality and safety.
Experiments test hypotheses.
The registry identifies approved configurations.
Routing, memory, RAG, and model selection optimize the workflow.
CI/CD controls integration and delivery.
Docker makes the runtime reproducible.
Staging validates deployment.
Monitoring turns failures into the next evaluation and improvement.
```

The project is successful when improvements are not merely claimed: every important change can be linked to a code version, configuration, evaluation dataset, measurable result, and documented trade-off.
