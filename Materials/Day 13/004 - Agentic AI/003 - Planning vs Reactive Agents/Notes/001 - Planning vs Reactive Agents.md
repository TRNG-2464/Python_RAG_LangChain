# Planning vs Reactive Agents

An agent has to decide what to do next, and there are two basic ways to organize that decision. A **reactive agent** decides one step at a time, looking at the latest result. A **planning agent** writes out the steps first, then carries them out. Neither is better in general; they fail differently, cost differently, and suit different tasks.

---

## Reactive Agents

A reactive agent runs the loop we already know: read everything so far, choose one action, observe the result, repeat. This is often called **ReAct** (reason + act), after the pattern of interleaving a thought, an action, and an observation. `create_agent` builds a reactive agent.

```
Task ──► model: "call get_order('A1001')"
         result: tracking=1Z999...
     ──► model: "call track_package('1Z999...')"
         result: Out for delivery
     ──► model: final answer
```

*Each decision is made fresh, with the latest result in view.*

The strength of this approach is adaptation. If a tool returns an error or something unexpected, the very next decision takes it into account. Nothing was committed to in advance, so there's nothing to throw away.

The weaknesses come from the same place. The model never steps back to consider the whole task, so on long jobs it can wander, repeat itself, or declare victory early. And every step goes to the full model with the full, growing history.

---

## Planning Agents

A planning agent splits the work in two. A **planner** call produces an ordered list of steps without executing anything. An **executor** then carries out each step, usually with a smaller context focused on just that step. This is often called **plan-and-execute**.

```python
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)

class Plan(BaseModel):
    steps: list[str] = Field(
        description="Ordered steps. Each step is one concrete action that a single tool call can complete."
    )

planner = llm.with_structured_output(Plan)

plan = planner.invoke([
    ("system",
     "Break the user's task into ordered steps. Do not perform them. "
     "Available tools: get_order(order_id), track_package(tracking_number), "
     "send_email(to, subject, body)."),
    ("human", "Find where order A1001 is and email the location to dana@example.com."),
])

for i, step in enumerate(plan.steps, 1):
    print(i, step)
```

*Asks the model for a structured plan up front, listing the tools it will have but executing nothing.*

The executor walks the plan. Each step gets its own short run of an agent, with the results of earlier steps passed in as plain text:

```python
# get_order, track_package: the order tools from the What Are AI Agents notes
# send_email: a @tool that sends a message
executor = create_agent(model=llm, tools=[get_order, track_package, send_email])

completed: list[tuple[str, str]] = []
for step in plan.steps:
    done_so_far = "\n".join(f"- {s}\n  result: {r}" for s, r in completed) or "(nothing yet)"
    run = executor.invoke({"messages": [{
        "role": "user",
        "content": f"Completed so far:\n{done_so_far}\n\nNow do exactly this step: {step}",
    }]})
    completed.append((step, run["messages"][-1].content))
```

*Executes each planned step in its own short agent run, passing forward only the summarized results of earlier steps.*

Two mechanics to notice. First, the plan is data — a Python list we can print, log, validate, or show to a person for approval before anything runs. Second, each executor run starts with a small context: one step plus a summary of prior results, not the full transcript of every earlier tool call.

---

## Recovering from a Bad Step

The plain loop above has a flaw: if step 1 discovers that order A1001 doesn't exist, steps 2 and 3 run anyway against a premise that's now false. A plan made before any results is a guess about what the results will be.

The fix is a **replanning** step. After each execution, the model reviews the original task, what's been done, and what remains, and either keeps the plan, revises it, or ends the run:

```python
class Replan(BaseModel):
    done: bool = Field(description="True if the task is complete or cannot be completed.")
    final_answer: str = Field(default="", description="The answer for the user, if done.")
    remaining_steps: list[str] = Field(default_factory=list, description="Revised remaining steps, if not done.")

replanner = llm.with_structured_output(Replan)
```

*Defines a structured decision the model makes after each step: finish, or continue with a revised list of steps.*

With replanning after every step, the design starts to look reactive again, just with an explicit plan carried in the state. That hybrid is common in practice: plan for structure, replan for recovery. How often to replan is the dial between the two approaches.

---

## Comparing the Two

| | Reactive | Planning |
|---|---|---|
| **Decides** | One step at a time, from the latest result | All steps up front, then executes |
| **Cost** | Every step re-sends the whole growing history to the main model | One planning call, then small per-step contexts; the executor can be a cheaper model |
| **Predictability** | The path emerges at runtime | The path is visible, and can be reviewed, before anything runs |
| **Recovery** | Immediate — the next decision sees the error | Only as good as the replanning; without it, a bad plan fails consistently |
| **Failure mode** | Wanders, loops, or stops early on long tasks | Commits to steps based on assumptions that turn out wrong |
| **Suits** | Short, exploratory tasks where each result shapes the next | Longer tasks with a knowable structure, or anything a person should approve first |

Predictability is often the deciding factor. A reactive agent's actions can only be approved one at a time, as they happen. A plan can be approved as a whole — "here are the five things I'm about to do" — which is a much better experience for anyone supervising an agent.

---

## Choosing

- **Few steps, uncertain path:** reactive. The planning call is overhead that buys nothing when there are two tool calls to make.
- **Many steps, clear structure:** planning, with replanning after steps that can fail.
- **Actions that need sign-off:** planning, so a person reviews the plan instead of every step.
- **Weak local model:** usually planning. Small models do better at "do this one step" than at holding a long goal in mind across a growing history.

LangChain also has a lightweight middle path: the built-in `TodoListMiddleware` gives a reactive `create_agent` a task-list tool, so the model can write down and update its own plan as part of the loop. The plan lives in the agent's state instead of in our code — more flexible, but no longer something we can review before execution starts.

---

## Key Takeaways

- Reactive agents (ReAct, `create_agent`) choose each step from the latest result; planning agents write the steps first, then execute them.
- Reactive agents adapt immediately but can wander, and every step re-sends the full history.
- Planning produces a plan as data: loggable, validatable, and approvable before anything runs.
- Plan-and-execute keeps each executor call small and can use a cheaper model for execution.
- A plan is a guess made before any results; add a replanning step after steps that can fail.
- Replanning after every step moves a planner toward reactive behavior — frequency of replanning is the dial between them.
