# Project Development Plan: NekoAgentCore Agent OS MVP

## 0. A Note to the Intern

This project is a smart work assistant for hard thinking tasks, such as reading papers, comparing ideas, checking evidence, and building a structured answer step by step. Your job is not to "make a chatbot"; your job is to help build a careful system that can plan work, look things up, remember what it found, admit when it is missing facts, and pause for human help instead of guessing.

---

## 1. Project Overview

### 1.1 Project Goals

This project builds an `Agent OS`, which means a software system that can run a long task in many small steps instead of trying to answer everything in one shot. It is meant for difficult knowledge work where facts, structure, and traceable reasoning matter more than fast chatting. The first target use case is helping with research-style work such as reading papers, comparing methods, and producing a writing plan backed by evidence.

### 1.2 System Architecture at a Glance (Text Version)

- `NekoAgentCore Agent OS`
  - `Interaction Layer`: This part talks to the user, receives missing information, and resumes paused work.
  - `Specification Layer`: This part stores the fixed stage plan called a Blueprint so the system knows which next moves are allowed.
  - `Control Layer`: This part decides what to do next, how much cost is allowed, which memory to load, and when to stop or ask for help.
    - `Strategist`: This part chooses the next logical action based on the current task state.
    - `ResourceManager`: This part decides how much time, model power, and budget the system should spend.
    - `MemoryRouter`: This part decides which saved information should be brought back into the active working area.
    - `CapabilityRouter`: This part decides which tools should be visible right now and hides the rest.
  - `Cognition Layer`: This part performs the main thinking work on the current small task.
    - `PromptBuilder`: This part turns structured state into a small, clear instruction for the model.
    - `ReasoningNode`: This part produces a draft answer or intermediate result for the current stage.
    - `ReflectionNode`: This part reviews the draft answer against rules and facts before the system trusts it.
  - `Investigation Layer`: This part searches, reads, compares, and collects evidence until the system has enough support for an answer.
  - `Capability Layer`: This part loads the right tool set for the current step and blocks unsafe tools when they are not needed.
  - `Memory Layer`: This part stores short-term context, event history, long-term facts, and global constants that must not be forgotten.
  - `Execution Layer`: This part runs models and tools, manages the sandbox, and carries out the work safely.
  - `Governance Layer`: This part records logs, measures quality, and enforces safety and approval rules.

### 1.3 Technology Stack

| Tool / Technology | Purpose | Beginner-Friendliness | Suggested Learning Resource |
| ----------------- | ------- | --------------------- | --------------------------- |
| `Python 3.12` | Main programming language for the whole system | ⭐⭐⭐⭐ | [Python Official Tutorial](https://docs.python.org/3/tutorial/) |
| `Pydantic v2` | Checks that shared state data has the right fields and types | ⭐⭐⭐⭐ | [Pydantic Documentation](https://docs.pydantic.dev/latest/) |
| `Typer` | Builds a simple command line program so you can run the system locally | ⭐⭐⭐⭐⭐ | [Typer Tutorial](https://typer.tiangolo.com/) |
| `SQLite` | Stores runs, events, and checkpoints in one local file | ⭐⭐⭐⭐⭐ | [SQLite Documentation](https://www.sqlite.org/docs.html) |
| `SQLModel` | Reads and writes SQLite data using Python classes instead of raw SQL first | ⭐⭐⭐⭐ | [SQLModel Tutorial](https://sqlmodel.tiangolo.com/tutorial/) |
| Custom Graph Runtime | Runs the system as connected steps with clear allowed paths | ⭐⭐⭐ | [Python Data Model Guide](https://docs.python.org/3/reference/datamodel.html) |
| `httpx` | Sends requests to model providers through one small gateway layer | ⭐⭐⭐⭐ | [HTTPX QuickStart](https://www.python-httpx.org/quickstart/) |
| `Rich` | Makes local terminal output easier to read while you debug | ⭐⭐⭐⭐⭐ | [Rich Documentation](https://rich.readthedocs.io/en/stable/) |
| `RapidFuzz` | Finds near-matches when words are spelled a little differently | ⭐⭐⭐⭐ | [RapidFuzz Documentation](https://rapidfuzz.github.io/RapidFuzz/) |
| `PyMuPDF` | Reads PDF files so the system can inspect paper content | ⭐⭐⭐ | [PyMuPDF Documentation](https://pymupdf.readthedocs.io/en/latest/) |
| `pytest` | Runs automated checks so you can confirm your code still works | ⭐⭐⭐⭐ | [pytest Getting Started](https://docs.pytest.org/en/stable/getting-started.html) |

---

## 2. Setting Up Your Development Environment (Read This on Day 1)

### 2.1 Hardware and OS Requirements

- A laptop or desktop with at least `16 GB` RAM.
- At least `30 GB` free disk space.
- A stable internet connection for downloading Python packages and reading documentation.
- Recommended operating system: `Ubuntu 24.04 LTS`.
- Acceptable alternatives: `macOS 14+` or `Windows 11 with WSL2 Ubuntu 24.04`.

### 2.2 Required Software (with exact version numbers)

The architecture report does not pin package versions, so this plan uses the exact baseline below for teaching and team consistency.

| Software | Exact Version | Why You Need It |
| -------- | ------------- | --------------- |
| `Git` | `2.43.0` | Downloads the code and tracks changes |
| `Python` | `3.12.8` | Runs the project |
| `uv` | `0.6.6` | Creates the project environment and installs Python packages |
| `SQLite` | `3.45.3` | Stores task history and checkpoints in one file |
| `Pydantic` | `2.10.6` | Validates shared state data |
| `Typer` | `0.15.1` | Creates the first command line entry point |
| `SQLModel` | `0.0.22` | Maps Python objects to SQLite tables |
| `httpx` | `0.28.1` | Sends model API requests |
| `Rich` | `13.9.4` | Prints readable logs in the terminal |
| `RapidFuzz` | `3.12.1` | Handles fuzzy text matching |
| `PyMuPDF` | `1.25.3` | Reads PDF content |
| `pytest` | `8.3.4` | Runs tests |

### 2.3 Step-by-Step Installation

This setup assumes `Ubuntu 24.04`. If you use another system, ask your mentor to help translate the package manager commands before continuing.

1. Install basic system tools.

```bash
sudo apt update
sudo apt install -y curl git sqlite3 build-essential
```

`sudo apt update` refreshes the list of available software packages on your computer.

`sudo apt install -y curl git sqlite3 build-essential` installs the basic tools this project needs: a downloader, version control, SQLite, and compiler tools for Python packages that need building.

1. Install `uv`.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

This downloads and installs `uv`, which is a small tool that manages Python versions, virtual environments, and packages.

1. Restart your terminal so the new `uv` command becomes available.

```bash
exec "$SHELL"
```

This closes the current shell process and starts a fresh one so your terminal can see the newly installed command.

1. Install the exact Python version used in this plan.

```bash
uv python install 3.12.8
```

This downloads Python `3.12.8` even if your computer came with an older or different Python version.

1. Clone the repository and enter it.

```bash
git clone <your-repository-url> NekoAgentCore
cd NekoAgentCore
```

`git clone <your-repository-url> NekoAgentCore` copies the project files from the shared repository to your computer.

`cd NekoAgentCore` moves your terminal into the project folder.

1. Create a private Python environment for this project.

```bash
uv venv --python 3.12.8
source .venv/bin/activate
```

`uv venv --python 3.12.8` creates a private Python environment so this project does not mix its packages with other projects on your computer.

`source .venv/bin/activate` turns that private environment on in your current terminal.

1. Install the starter Python packages for the MVP.

```bash
uv pip install pydantic==2.10.6 typer==0.15.1 sqlmodel==0.0.22 httpx==0.28.1 rich==13.9.4 rapidfuzz==3.12.1 pymupdf==1.25.3 pytest==8.3.4
```

This installs the first set of Python libraries you need to build the early version of the system.

1. Create the starting folder structure.

```bash
mkdir -p agent_os/app agent_os/runtime agent_os/cognition agent_os/investigation agent_os/memory agent_os/tools agent_os/models agent_os/observability agent_os/evaluation tests
```

This creates the top-level folders from the architecture report so you start with the correct project shape.

### 2.4 Environment Verification Checklist

- [ ] Step 1: Run `git --version` - expected output contains `git version 2.43.0`
- [ ] Step 2: Run `uv --version` - expected output contains `uv 0.6.6`
- [ ] Step 3: Run `python --version` - expected output contains `Python 3.12.8`
- [ ] Step 4: Run `sqlite3 --version` - expected output starts with `3.45`
- [ ] Step 5: Run `python -c "import pydantic; print(pydantic.__version__)"` - expected output is `2.10.6`
- [ ] Step 6: Run `python -c "import typer, sqlmodel, httpx, rich, rapidfuzz, fitz; print('ok')"` - expected output is `ok`

> ⚠️ Common Pitfalls:
>
> 1. You forget to run `source .venv/bin/activate`, so Python cannot find the installed packages. Fix: run the command again and then repeat the verification checklist.
> 2. You use the system Python instead of `3.12.8`, which causes version mismatch bugs. Fix: run `python --version`; if it is wrong, recreate the virtual environment with `uv venv --python 3.12.8`.
> 3. You copy the repository URL incorrectly and `git clone` fails. Fix: copy the full URL again from your team source and retry the command.

---

## 3. Code Style Quick-Reference (Read Before Writing Any Code)

### 3.1 Naming Conventions

| Case | ❌ Wrong Example | ✅ Correct Example |
| ---- | ---------------- | ----------------- |
| Variable | `CurrentNode = "reasoning"` | `current_node = "reasoning"` |
| Function | `BuildState()` | `build_state()` |
| Class | `reasoning_node` | `ReasoningNode` |
| File name | `ReasoningNode.py` | `reasoning_node.py` |
| Config key | `"CurrentNode"` | `"current_node"` |
| Factory function | `makeStateModel()` in one file and `build_model()` in another | `build_state_model()` everywhere |

### 3.2 File and Directory Structure

```text
NekoAgentCore/
  docs/
    Agent系统架构设计报告.md
    engineering-style-guide.md
    project-development-plan.md
  agent_os/
    app/
      cli.py
      api/
      services/
      schemas/
    runtime/
      graph/
        engine.py
        edges.py
      routing/
        meta_router.py
      state/
        models.py
      checkpoint/
        repository.py
      policies/
        budget_policy.py
      epistemic_guard/
        guard.py
    cognition/
      prompt_builder/
        builder.py
      reasoning/
        reasoning_node.py
      reflection/
        reflection_node.py
      strategist/
        strategist.py
      resource_manager/
        resource_manager.py
      memory_router/
        memory_router.py
    investigation/
      query_builder/
        query_builder.py
      recall/
        hybrid_recall.py
      rerank/
        reranker.py
      extract/
        extractor.py
      micro_graph/
        micro_graph.py
    memory/
      ram/
        working_ram.py
      cache/
        episodic_cache.py
      disk/
        semantic_disk.py
      blackboard/
        global_blackboard.py
      compression/
        compressor.py
    tools/
      capability_loader/
        loader.py
      registry/
        registry.py
      adapters/
        base.py
      sandbox/
        sandbox.py
    models/
      gateway/
        client.py
      providers/
        base.py
      pricing/
        rules.py
    observability/
      tracing/
        trace_logger.py
      logging/
        app_logger.py
      metrics/
        counters.py
    evaluation/
      datasets/
      scenarios/
      regression/
  tests/
    runtime/
    cognition/
    investigation/
    memory/
    tools/
```

### 3.3 Comment Standards

Ready-to-copy module docstring:

```python
"""Build and validate the shared run state for the Agent OS.

This module owns the data shapes that move between runtime nodes.
Keep new fields here instead of creating hidden state in many files.
"""
```

Ready-to-copy function docstring:

```python
def build_checkpoint_path(run_id: str) -> str:
    """Return the file path for one saved run snapshot."""
```

Ready-to-copy invariant comment:

```python
# Invariant: only the routing layer may change `current_node`.
```

Ready-to-copy initialization order comment:

```python
# Initialization order matters:
# 1. Load config.
# 2. Build logger.
# 3. Build storage.
# 4. Build runtime nodes.
```

### 3.4 Top Violations to Avoid

1. **Hardcoding Configuration Inside Core Logic**: Do not put model names, file paths, or stage rules directly inside the main runtime code when a config value or factory can hold them.
2. **Circular Dependencies**: Do not make two layers import each other, because this creates confusing start-up bugs and breaks the one-way design rule.
3. **Object Creation During Import**: Do not create databases, model clients, or tool objects at the top of a file as soon as Python imports it; build them in one explicit `build_*` function instead.
4. **Hidden Shared State Across Many Files**: Do not quietly store important global values in random modules; keep shared state in the official runtime state or one clearly named context object.
5. **Scattered Data Mapping Rules**: Do not rewrite the same field rename or cleanup logic in many places; create one mapping function and reuse it.

---

## 4. Module Development Guide

<!-- markdownlint-disable MD022 MD024 -->

### 4.1 Global State Model

#### What this module does
This module stores the shared record of what the whole system is doing right now.

#### Inputs / Outputs

- Input: user task text, active stage name, loaded memory references, budget values
- Output: one validated `RunState` object that every other module can read

#### Development Steps

1. Open `agent_os/runtime/state/models.py`.
2. Create a `RunState` class with `Pydantic` so missing fields are caught early.
3. Add smaller child classes such as `BlueprintState`, `MemoryRefs`, `RoutingState`, and `UncertaintyState` instead of placing everything in one giant class.
4. Use `snake_case` field names so the Python code and saved JSON use the same names.
5. Open `tests/runtime/test_state_models.py`.
6. Write one test that creates a valid `RunState` and one test that confirms invalid data raises an error.
7. Run the test file before moving on.

#### Code Example

```python
from pydantic import BaseModel, Field


class MemoryRefs(BaseModel):
    """Pointers to saved information used by the current run."""

    ram_refs: list[str] = Field(default_factory=list)
    cache_refs: list[str] = Field(default_factory=list)
    disk_refs: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    """Shared record of what the system is doing right now."""

    run_id: str
    goal: str
    current_node: str = "interaction"
    status: str = "running"
    memory: MemoryRefs = Field(default_factory=MemoryRefs)
```

#### Definition of Done

- Running `pytest tests/runtime/test_state_models.py -q` prints `2 passed`
- Saving `RunState(run_id="demo", goal="read one paper")` produces valid JSON
- Every field name is `snake_case`

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are forgetting `default_factory` for list fields and storing ad-hoc values outside the shared state model.

### 4.2 Graph Runtime

#### What this module does
This module moves the system from one step to the next using explicit, legal paths.

#### Inputs / Outputs

- Input: current `RunState`, registered node functions, edge rules
- Output: next state plus the name of the next node to execute

#### Development Steps

1. Open `agent_os/runtime/graph/engine.py`.
2. Create a `NodeResult` object that always returns `next_node` and `state_delta`.
3. Add a `GraphEngine` class with a `run_one_step()` method.
4. In `run_one_step()`, load the current node handler from a registry instead of using a long `if` chain.
5. Handle straight-line paths directly in code and reserve branching paths for the control layer.
6. Open `tests/runtime/test_graph_engine.py`.
7. Write a test for one straight path and one blocked illegal edge.

#### Code Example

```python
from dataclasses import dataclass

from agent_os.runtime.state.models import RunState


@dataclass(frozen=True)
class NodeResult:
    next_node: str
    state_delta: dict[str, object]


class GraphEngine:
    """Run one node and return the next legal state."""

    def apply_delta(self, state: RunState, state_delta: dict[str, object]) -> RunState:
        return state.model_copy(update=state_delta)
```

#### Definition of Done

- Running `pytest tests/runtime/test_graph_engine.py -q` prints `2 passed`
- A node can return a legal next step without editing the original state object in place
- Illegal edges raise a clear error message

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are hardcoding edge logic in many files and mutating the same state object in place so bugs become hard to track.

### 4.3 Interaction Layer

#### What this module does
This module receives work from the user and gives the user a safe way to answer paused questions later.

#### Inputs / Outputs

- Input: command line arguments, user task text, user follow-up answers
- Output: a normalized task request stored in `RunState`

#### Development Steps

1. Open `agent_os/app/cli.py`.
2. Create a `Typer` app with one command named `start-run`.
3. Accept plain text input such as a task goal and optional source file paths.
4. Convert the raw command line values into one clean request object in `agent_os/app/schemas/requests.py`.
5. Add a second command named `resume-run` that accepts a saved `run_id`.
6. Open `tests/app/test_cli.py`.
7. Write one test for `start-run` and one test for `resume-run`.

#### Code Example

```python
import typer

app = typer.Typer()


@app.command("start-run")
def start_run(goal: str) -> None:
    """Start one local Agent OS run."""

    print(f"Starting run for goal: {goal}")
```

#### Definition of Done

- Running `python -m agent_os.app.cli start-run "read one paper"` prints `Starting run for goal: read one paper`
- Running `pytest tests/app/test_cli.py -q` prints `2 passed`
- All raw command line values are converted into one request object before they reach runtime code

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are putting business logic inside the CLI file and accepting too many raw parameters without normalizing them first.

### 4.4 Blueprint Module

#### What this module does
This module stores the fixed stage plan that tells the system which big steps are allowed.

#### Inputs / Outputs

- Input: task goal, stage definitions, allowed exits, quality rules
- Output: one active Blueprint stage and the legal next stages

#### Development Steps

1. Open `agent_os/runtime/state/blueprint_models.py` or create it if it does not exist.
2. Define `BlueprintNode` with fields such as `node_id`, `goal`, `allowed_exits`, and `subgraph_template`.
3. Define `BlueprintGraph` as a list or dictionary of `BlueprintNode` objects.
4. Add a loader function in `agent_os/runtime/graph/blueprint_loader.py` named `build_blueprint_graph()`.
5. Start with one sample flow: `literature_scan -> idea_summary -> writing_plan`.
6. Open `tests/runtime/test_blueprint_loader.py`.
7. Write a test that confirms illegal stage jumps are rejected.

#### Code Example

```python
from pydantic import BaseModel, Field


class BlueprintNode(BaseModel):
    """One allowed stage in the fixed project plan."""

    node_id: str
    goal: str
    allowed_exits: list[str] = Field(default_factory=list)
    subgraph_template: str
```

#### Definition of Done

- Running `pytest tests/runtime/test_blueprint_loader.py -q` prints `2 passed`
- A sample blueprint can be loaded from plain data
- The graph clearly lists allowed exits for every stage

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are writing the Blueprint as free-form text only and forgetting to list legal exits for each stage.

### 4.5 Meta Control Module

#### What this module does
This module decides what the system should do next when there is more than one possible path.

#### Inputs / Outputs

- Input: current `RunState`, current Blueprint stage, budget status, uncertainty status
- Output: a routing decision with `next_node`, confidence, memory mounts, and tool profile

#### Development Steps

1. Open `agent_os/cognition/strategist/strategist.py`.
2. Create a small decision model named `RoutingDecision`.
3. Add a `Strategist` class that chooses between `reasoning`, `investigation`, `reflection`, or `break`.
4. Keep budget logic in `agent_os/cognition/resource_manager/resource_manager.py` instead of mixing it into the strategist.
5. Keep memory loading advice in `agent_os/cognition/memory_router/memory_router.py`.
6. Write tests that cover one high-confidence route and one low-confidence route.
7. Make the module return data, not direct side effects.

#### Code Example

```python
from pydantic import BaseModel


class RoutingDecision(BaseModel):
    """Describe what the control layer decided to do next."""

    next_node: str
    confidence: float
    tool_profile: str
```

#### Definition of Done

- Running `pytest tests/cognition/test_strategist.py -q` prints `2 passed`
- The control layer returns a structured decision object instead of scattered values
- Low-confidence decisions can be redirected to review or break logic

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are mixing budget logic into every decision rule and letting the controller generate long user-facing text instead of returning structured data.

### 4.6 Prompt Builder

#### What this module does
This module turns structured state into a short, clear instruction for the model.

#### Inputs / Outputs

- Input: goal, active Blueprint stage, selected facts, memory summary
- Output: one compact prompt string or structured message list

#### Development Steps

1. Open `agent_os/cognition/prompt_builder/builder.py`.
2. Create a `build_reasoning_prompt()` function.
3. Feed it only the stage goal, relevant facts, and current payload instead of the full history.
4. Add a second function named `build_reflection_prompt()` so review rules stay separate from reasoning rules.
5. Keep fixed prompt fragments in small constants or template files rather than writing giant strings inline.
6. Open `tests/cognition/test_prompt_builder.py`.
7. Write tests that confirm missing optional fields do not break prompt creation.

#### Code Example

```python
from agent_os.runtime.state.models import RunState


def build_reasoning_prompt(state: RunState) -> str:
    """Build a short prompt for the current reasoning step."""

    return (
        f"Goal: {state.goal}\n"
        f"Current node: {state.current_node}\n"
        "Use only accepted facts and state what is still missing."
    )
```

#### Definition of Done

- Running `pytest tests/cognition/test_prompt_builder.py -q` prints `2 passed`
- The prompt builder can work from structured state alone
- Reasoning and reflection prompts are built by different functions

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are stuffing the whole run history into every prompt and mixing review instructions into generation instructions.

### 4.7 Reasoning Node

#### What this module does
This module creates the current draft answer for the small task in front of the system.

#### Inputs / Outputs

- Input: current stage goal, prompt, accepted facts, active payload
- Output: a structured stage result plus a flag that says whether more evidence is needed

#### Development Steps

1. Open `agent_os/cognition/reasoning/reasoning_node.py`.
2. Create a `ReasoningNode` class with one public method named `run()`.
3. Pass in the prompt builder and model gateway as constructor arguments so the node does not create them by itself.
4. Make `run()` return a structured object such as `ReasoningResult`.
5. Add fields such as `draft_text`, `missing_questions`, and `needs_investigation`.
6. Open `tests/cognition/test_reasoning_node.py`.
7. Use a fake model client in the test so the test does not depend on the internet.

#### Code Example

```python
from pydantic import BaseModel, Field


class ReasoningResult(BaseModel):
    """Result produced by the reasoning node."""

    draft_text: str
    missing_questions: list[str] = Field(default_factory=list)
    needs_investigation: bool = False
```

#### Definition of Done

- Running `pytest tests/cognition/test_reasoning_node.py -q` prints `2 passed`
- The node returns structured output instead of raw text only
- The node can explicitly request investigation when it lacks facts

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are letting the node change routing state directly and trusting raw model text without wrapping it in a typed result.

### 4.8 Reflection Node

#### What this module does
This module checks whether the draft answer actually meets the stage rules and uses enough evidence.

#### Inputs / Outputs

- Input: draft result, Blueprint checklist, accepted facts, known symbols or constants
- Output: a review verdict such as `approved`, `retry`, or `need_more_evidence`

#### Development Steps

1. Open `agent_os/cognition/reflection/reflection_node.py`.
2. Create a `ReflectionVerdict` model with fields for `status`, `issues`, and `next_action`.
3. Keep the reflection prompt separate from the reasoning prompt.
4. Pass only the draft result, Blueprint checklist, and approved facts to this node.
5. Do not send the full hidden reasoning chain to this node.
6. Open `tests/cognition/test_reflection_node.py`.
7. Write tests for one passing case and one failing case.

#### Code Example

```python
from pydantic import BaseModel, Field


class ReflectionVerdict(BaseModel):
    """Review result for one stage output."""

    status: str
    issues: list[str] = Field(default_factory=list)
    next_action: str
```

#### Definition of Done

- Running `pytest tests/cognition/test_reflection_node.py -q` prints `2 passed`
- Reflection reads only review inputs, not the full hidden work history
- The verdict clearly says what should happen next

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are giving reflection too much context and writing vague review outputs such as "looks fine" instead of a clear next action.

### 4.9 Investigation Subgraph

#### What this module does
This module searches for evidence, reads useful sources, and returns a smaller fact package to the main system.

#### Inputs / Outputs

- Input: retrieval goal, search keywords, file or paper sources, current uncertainty
- Output: distilled facts, source references, and a status of `enough_evidence` or `need_more_evidence`

#### Development Steps

1. Open `agent_os/investigation/query_builder/query_builder.py`.
2. Create a function that turns one retrieval goal into several search forms, such as natural language text and exact terms.
3. Open `agent_os/investigation/recall/hybrid_recall.py`.
4. Build a simple local first version that combines keyword search, fuzzy matching, and direct file reads.
5. Open `agent_os/investigation/rerank/reranker.py` and add a small scoring function so the best matches rise to the top.
6. Open `agent_os/investigation/extract/extractor.py` and write functions that return only the needed facts, not the whole source.
7. Open `agent_os/investigation/micro_graph/micro_graph.py` and store claim-to-fact links for the current run only.
8. Write tests that confirm the module stops once enough evidence is found.

#### Code Example

```python
from pydantic import BaseModel, Field


class RetrievalIntent(BaseModel):
    """Describe what the investigation step is trying to find."""

    intent: str
    dense_query: str
    sparse_keywords: list[str] = Field(default_factory=list)
    exact_terms: list[str] = Field(default_factory=list)
```

#### Definition of Done

- Running `pytest tests/investigation -q` prints only passing tests
- The module can turn one retrieval goal into more than one search form
- Returned data contains distilled facts and source references instead of raw dumps

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are returning huge unreadable source text blocks and forgetting to stop the loop after enough evidence is already available.

### 4.10 Memory System

#### What this module does
This module stores what the system needs now, what happened earlier, what should be kept long term, and what must never be forgotten.

#### Inputs / Outputs

- Input: stage outputs, important facts, checkpoints, event summaries
- Output: saved memory records in RAM, cache, disk, and blackboard stores

#### Development Steps

1. Open `agent_os/memory/ram/working_ram.py`.
2. Build a small class that stores only the minimum context needed for the current node.
3. Open `agent_os/memory/cache/episodic_cache.py` and save step-by-step history there.
4. Open `agent_os/memory/disk/semantic_disk.py` and store reusable fact summaries there.
5. Open `agent_os/memory/blackboard/global_blackboard.py` and keep shared constants such as approved terms there.
6. Open `agent_os/memory/compression/compressor.py` and create `L1`, `L2`, and `L3` summary levels.
7. Write tests that confirm each layer stores a different level of detail.

#### Code Example

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryMount:
    """One request to load a saved memory item into active work."""

    source: str
    ref_id: str
    detail_level: str
```

#### Definition of Done

- Running `pytest tests/memory -q` prints only passing tests
- The system can request memory by reference instead of copying all old text into RAM
- `L1`, `L2`, and `L3` summaries are stored separately

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are treating memory as one giant text blob and forgetting that the blackboard should hold stable shared facts only.

### 4.11 Model Gateway

#### What this module does
This module gives the rest of the system one consistent way to talk to language models.

#### Inputs / Outputs

- Input: model name, prompt or message list, timeout, budget rules
- Output: one normalized response object

#### Development Steps

1. Open `agent_os/models/providers/base.py`.
2. Define a base interface that every provider wrapper must follow.
3. Open `agent_os/models/gateway/client.py`.
4. Create a small gateway class that accepts a provider object instead of knowing provider details itself.
5. Return a normalized response with text, token counts, and raw metadata.
6. Keep pricing logic in `agent_os/models/pricing/rules.py`.
7. Write tests with a fake provider that returns a fixed answer.

#### Code Example

```python
from pydantic import BaseModel


class ModelResponse(BaseModel):
    """Normalized model output used by the rest of the system."""

    text: str
    input_tokens: int
    output_tokens: int
```

#### Definition of Done

- Running `pytest tests/models -q` prints only passing tests
- The reasoning node can call the gateway without knowing provider-specific details
- The response shape is the same for fake and real providers

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are letting provider-specific code leak into the reasoning node and forgetting to return token usage for later budget checks.

### 4.12 Capability Loader and Tool Runtime

#### What this module does
This module decides which tools are visible right now and runs them safely.

#### Inputs / Outputs

- Input: current node type, permission level, budget level, requested tool action
- Output: a loaded tool list and the result of one safe tool execution

#### Development Steps

1. Open `agent_os/tools/registry/registry.py`.
2. Define a `ToolSpec` object with name, description, permission level, and callable handler.
3. Open `agent_os/tools/capability_loader/loader.py`.
4. Load only the tool groups needed for the current stage, such as read-only tools for investigation.
5. Open `agent_os/tools/sandbox/sandbox.py`.
6. Add path allow-lists, timeout rules, and logging for every tool call with side effects.
7. Write tests for read-only tool loading and blocked high-risk tool calls.

#### Code Example

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """Describe one tool the runtime may expose."""

    name: str
    description: str
    permission_level: str
```

#### Definition of Done

- Running `pytest tests/tools -q` prints only passing tests
- The investigation flow only sees read-only tools by default
- A blocked high-risk tool call writes a log entry and returns a clear refusal

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are exposing every tool at once and skipping logs for actions that change files or run commands.

### 4.13 Checkpoint, Break, and Human Recovery

#### What this module does
This module saves progress, pauses safely, asks the smallest useful human question, and resumes later.

#### Inputs / Outputs

- Input: current `RunState`, uncertainty type, pending user question
- Output: saved checkpoint plus a small break report for the human

#### Development Steps

1. Open `agent_os/runtime/checkpoint/repository.py`.
2. Save the full run state to SQLite and a snapshot file.
3. Open `agent_os/runtime/epistemic_guard/guard.py`.
4. Add clear uncertainty types such as `missing_evidence`, `tool_unavailable`, `conflicting_evidence`, and `user_input_required`.
5. When the system cannot continue safely, create a `BreakReport` object instead of guessing.
6. Expose a `resume_run()` path in the interaction layer that reloads the last checkpoint.
7. Write tests for pause and resume.

#### Code Example

```python
from pydantic import BaseModel


class BreakReport(BaseModel):
    """Small human-readable summary shown when the system pauses."""

    uncertainty_type: str
    known_now: str
    missing_now: str
    question_for_user: str
```

#### Definition of Done

- Running `pytest tests/runtime/test_checkpoint_resume.py -q` prints `2 passed`
- A paused run writes both a database record and a snapshot file
- The break report explains what is known, what is missing, and what the user should answer

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are saving too little state to resume correctly and writing vague user questions such as "Please help" instead of one specific missing fact.

### 4.14 Governance and Evaluation

#### What this module does
This module records what happened, measures whether the system behaved correctly, and helps catch regressions after code changes.

#### Inputs / Outputs

- Input: trace events, tool calls, node results, evaluation scenarios
- Output: structured logs, score summaries, and regression test results

#### Development Steps

1. Open `agent_os/observability/tracing/trace_logger.py`.
2. Log every node start, node end, tool call, blocked action, and checkpoint save with one trace identifier.
3. Open `agent_os/observability/logging/app_logger.py` and create one standard logger builder.
4. Open `agent_os/evaluation/scenarios/` and add a few fixed test tasks such as `paper_summary` and `compare_methods`.
5. Open `agent_os/evaluation/regression/runner.py`.
6. Write a small runner that executes saved scenarios and compares the outputs to expected checks.
7. Run regression checks before every major merge.

#### Code Example

```python
from pydantic import BaseModel


class TraceEvent(BaseModel):
    """One structured event in the run history."""

    trace_id: str
    event_type: str
    message: str
```

#### Definition of Done

- Running `pytest tests/observability tests/evaluation -q` prints only passing tests
- Every run produces a trace identifier and node-level event logs
- At least two regression scenarios can be executed locally

> ⚠️ Watch out: the 2 most common mistakes interns make in this module are writing only pretty console output without saved structured logs and skipping regression checks after refactors.

---

## 5. Task Breakdown and Timeline

<!-- markdownlint-enable MD022 MD024 -->

### 5.1 Sprint Plan

| Sprint | Days | Target Modules | Deliverable | Acceptance Criteria |
| ------ | ---- | -------------- | ----------- | ------------------- |
| Sprint 1 | Day 1-4 | Setup + Style Guide + Project Skeleton | Working environment and correct folder layout | All setup checks pass and the folder tree matches the plan |
| Sprint 2 | Day 5-8 | Global State Model | `RunState` and child models with tests | `pytest tests/runtime/test_state_models.py -q` shows `2 passed` |
| Sprint 3 | Day 9-13 | Graph Runtime + Checkpoint basics | One-step runtime loop and basic save/load | Straight path execution works and checkpoint file is written |
| Sprint 4 | Day 14-18 | Interaction Layer + Blueprint Module | CLI entry points and first fixed stage graph | `start-run` works and one sample Blueprint loads correctly |
| Sprint 5 | Day 19-24 | Meta Control + Prompt Builder | Structured routing decisions and prompt builders | Routing returns typed data and prompt tests pass |
| Sprint 6 | Day 25-30 | Reasoning Node + Reflection Node | Draft generation and review verdict flow | Reasoning and reflection tests both pass |
| Sprint 7 | Day 31-36 | Investigation Subgraph + Capability Loader | Local evidence search flow with safe tool loading | Investigation returns distilled facts and only safe tools are exposed |
| Sprint 8 | Day 37-41 | Memory System | RAM, cache, disk, and blackboard layers | Memory tests pass and summary levels `L1`, `L2`, `L3` work |
| Sprint 9 | Day 42-46 | Model Gateway + Governance | Normalized model responses, logs, and trace events | Gateway tests pass and each run emits trace events |
| Sprint 10 | Day 47-52 | Integration + Evaluation + Bug Fixing | End-to-end MVP demo from task input to review result | One full demo scenario runs from CLI start to final reviewed output |

### 5.2 A Typical Workday

Use this schedule as a default work rhythm:

- `09:00-09:30`: Read the architecture report section and style guide rule that match today’s module.
- `09:30-10:00`: Re-read the previous day’s code and write down what still feels unclear.
- `10:00-12:00`: Implement one small piece only, such as one data model or one function.
- `12:00-13:00`: Lunch break.
- `13:00-14:00`: Write or update tests for the code you added in the morning.
- `14:00-15:00`: Run the code, read errors carefully, and fix one problem at a time.
- `15:00-15:30`: Update comments or docstrings where the logic is easy to misunderstand.
- `15:30-16:00`: Run the module tests again and capture the results in your notes.
- `16:00-16:30`: Commit your work with a small, clear message.
- `16:30-17:00`: Ask for review if the module definition of done is complete, or write down the exact blocker if it is not.

---

## 6. Testing and Self-Review

### 6.1 How to Self-Test Each Module

- `Global State Model`: Create valid and invalid state objects and confirm validation works.
- `Graph Runtime`: Run a straight path and one illegal edge path.
- `Interaction Layer`: Start a run and resume a run from the command line.
- `Blueprint Module`: Load one sample blueprint and confirm every stage lists allowed exits.
- `Meta Control Module`: Feed in one state with enough facts and one with low confidence; confirm the next node differs correctly.
- `Prompt Builder`: Build prompts from a small state and confirm missing optional fields do not crash the code.
- `Reasoning Node`: Use a fake model client and confirm the node returns a typed `ReasoningResult`.
- `Reflection Node`: Confirm weak drafts are rejected with a clear reason.
- `Investigation Subgraph`: Confirm the search loop stops when enough evidence is found.
- `Memory System`: Save and reload one item from each memory layer.
- `Model Gateway`: Swap fake and real providers and confirm the response object keeps the same shape.
- `Capability Loader and Tool Runtime`: Confirm read-only tools load in read-only stages and blocked tools are rejected safely.
- `Checkpoint, Break, and Human Recovery`: Save a paused run, reload it, and continue work.
- `Governance and Evaluation`: Confirm a trace log is written and one regression scenario can run end to end.

### 6.2 Integration Testing Steps

1. Start with one simple task such as "read one paper abstract and produce three key points."
2. Run `start-run` from the CLI and confirm a new `run_id` is created.
3. Confirm the system creates an initial `RunState`.
4. Confirm the Blueprint stage becomes active.
5. Confirm the reasoning node can produce a draft result.
6. Force one missing-evidence case and confirm the investigation flow starts.
7. Confirm distilled facts return to the main runtime instead of raw source dumps.
8. Confirm the reflection node either approves or requests a retry.
9. Force one break condition and confirm the system asks one focused user question.
10. Resume the run and confirm it continues from the saved checkpoint instead of starting over.

### 6.3 Pre-Commit Checklist

- [ ] Do all names follow the naming conventions?
- [ ] Are necessary comments in place for tricky logic only?
- [ ] Are there any unresolved TODOs left in the code?
- [ ] Did you avoid creating objects at import time?
- [ ] Did you keep new configuration values out of core logic?
- [ ] Did you update or add tests for the code you changed?
- [ ] Did all relevant tests pass locally?
- [ ] Did you avoid circular imports?
- [ ] Did you keep shared state inside the official runtime models or context objects?
- [ ] If a tool can change files or run commands, did you log and restrict it?

---

## 7. FAQ and Beginner Traps

**Q: What is the easiest way to understand this whole project?**  
A: Think of it as a careful assistant that works in stages: it receives a task, plans allowed steps, works on one small step, checks itself, searches for evidence if needed, saves progress, and asks for help when blocked.

**Q: What is a "state model" in plain English?**  
A: It is a shared record of the run, like a paper form that tells every module what the current goal is, which step is active, what facts are already accepted, and what is still missing.

**Q: Why can I not just pass raw text between modules?**  
A: Raw text is easy to lose, misread, or change by accident. Structured state is safer because each piece of information has a named place.

**Q: What is the difference between `Main Graph`, `Blueprint`, and `Sub-graph`?**  
A: `Main Graph` is the big traffic map for the whole system, `Blueprint` is the fixed stage plan used when strict order matters, and a `Sub-graph` is the smaller working routine used to complete one Blueprint stage.

**Q: Why are `Reasoning` and `Reflection` separate?**  
A: One writes the draft and the other checks the draft. Keeping them separate reduces the chance that the system blindly agrees with its own first answer.

**Q: What should I do if I do not understand a file name from the folder tree?**  
A: Open the folder, read the module docstring first, and compare the file's job to the architecture report before changing anything.

**Q: Why does the style guide forbid object creation during import?**  
A: Because it creates hidden side effects. A file should not quietly open a database or call a model just because Python read the file.

**Q: What command should I run first when something breaks?**  
A: Run the smallest related test first, for example `pytest tests/runtime/test_state_models.py -q`, so you check one module at a time instead of the whole project at once.

**Q: How do I know whether to add a new field to `RunState`?**  
A: Add a field only if more than one module needs the value during a run and the value truly belongs to shared runtime state.

**Q: What do I do if the system does not have enough evidence to continue?**  
A: Do not invent facts. Trigger the investigation flow or create a break report with a focused question for the user.

**Q: Why do we save checkpoints?**  
A: Long tasks fail sometimes. A checkpoint lets the system continue from a saved state instead of wasting time by starting over.

**Q: I changed one module and now several tests fail. What should I do?**  
A: Stop adding new code, read the first failing test carefully, fix one failure at a time, and rerun only the affected tests until the failures are gone.

**Q: How often should I commit my work?**  
A: Commit whenever one small unit is finished and tested, such as one data model, one node, or one working CLI command.

**Q: What should I do before asking my mentor for help?**  
A: Write down the exact command you ran, copy the exact error message, note what you expected to happen, and list the two or three fixes you already tried.

---

## 8. Learning Resources and How to Ask for Help

### 8.1 Must-Read Materials (in priority order)

1. [Architecture Report](./Agent%E7%B3%BB%E7%BB%9F%E6%9E%B6%E6%9E%84%E8%AE%BE%E8%AE%A1%E6%8A%A5%E5%91%8A.md)
2. [Engineering Style Guide](./engineering-style-guide.md)
3. [Python Official Tutorial](https://docs.python.org/3/tutorial/)
4. [Pydantic Documentation](https://docs.pydantic.dev/latest/)
5. [Typer Tutorial](https://typer.tiangolo.com/)
6. [SQLModel Tutorial](https://sqlmodel.tiangolo.com/tutorial/)
7. [pytest Getting Started](https://docs.pytest.org/en/stable/getting-started.html)

### 8.2 Debugging Order When Something Goes Wrong

1. Search this document's FAQ first.
2. Then consult [the architecture report](./Agent%E7%B3%BB%E7%BB%9F%E6%9E%B6%E6%9E%84%E8%AE%BE%E8%AE%A1%E6%8A%A5%E5%91%8A.md) to check whether you misunderstood the module's role.
3. Then consult [the engineering style guide](./engineering-style-guide.md) to check whether the bug came from a broken design rule.
4. Then rerun the smallest related test.
5. Finally, ask your mentor and include: a screenshot of the error, the exact command you ran, the file you changed, and a short list of what you already tried.

---

Plan version: v1.0 | Generated: 2026-03-24 | Audience: zero-background intern
