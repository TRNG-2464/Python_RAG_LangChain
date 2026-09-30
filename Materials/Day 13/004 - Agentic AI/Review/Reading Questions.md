# Agentic AI — Reading Questions

## What Are AI Agents

1. A chain can call a tool at a fixed step and still not be an agent. What property does an agent have that such a chain lacks?
2. What has to be true about a task's steps for it to actually need an agent rather than a chain?
3. The model ends an agent run by replying without a tool call. Why do we still need a hard limit on the number of steps?
4. Why does adding steps to an agent's loop make it less reliable, not just slower and more expensive?

## Agentic Workflows

1. In an agentic workflow the model does real work at every step, yet the flow stays predictable enough to test. What does our code control that the model doesn't?
2. What does splitting a task into two chained calls give us that one large prompt asking for everything can't?
3. Why do we constrain a router's classification to a fixed set of values rather than letting the model name any destination it likes?
4. When a coordinating agent delegates to a specialist agent wrapped as a tool, what does the coordinator gain, and what does it give up?

## Planning vs Reactive Agents

1. A reactive agent's main strength and its main weakness on long tasks come from the same design choice. What is that choice, and how does it produce both?
2. In plan-and-execute, the plan is a piece of data our code holds before anything runs. Why does that matter to a person supervising the agent?
3. Why is a plan made entirely before execution fragile when one of its steps can fail?
4. Why do smaller local models often do better in a plan-and-execute design than as reactive agents?

## Human-in-the-Loop

1. Why can putting too many actions behind human approval end up worse than gating only a few?
2. Why should a reviewer see the tool call's actual arguments rather than the model's description of what it plans to do?
3. When a reviewer rejects a tool call, why do we send that rejection back to the model as a tool result instead of just skipping the call?
4. Why does a real approval pause in a web application depend on saving the agent's state rather than waiting for an answer?

## Multi-Step Reasoning

1. Why does it matter whether a model writes its reasoning before or after its answer — in a free-text reply or in a structured-output schema?
2. The model has no memory between calls. How does it use a tracking number it received two steps earlier in an agent run?
3. Why does an agent's input-token cost grow faster than its number of steps?
4. When our code orchestrates separate model calls instead of running one agent loop, what control do we gain over context cost?
