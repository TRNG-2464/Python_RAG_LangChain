# Agentic Workflows

Between a single model call and a fully autonomous agent sits a wide middle ground: **agentic workflows**, where the work is split into several model-driven steps but *our code* still defines how those steps connect. Most production LLM systems live here. They get much of the benefit of multiple model calls while keeping the flow predictable enough to test.

The useful distinction:

- A **workflow** orchestrates model calls along paths we wrote in code. The model fills in each step; it doesn't choose the route (or chooses only among routes we enumerated).
- An **agent** chooses its own route at runtime.

Both are built from the same parts. The patterns below are the common ways of connecting them.

---

## Chaining

**Chaining** feeds one call's output into the next. Each call does one narrow job, which makes each easier to prompt and easier to check.

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)

extract = ChatPromptTemplate.from_template(
    "List every action item in this meeting transcript, one per line, "
    "in the form 'OWNER: task'. Output only the list.\n\n{transcript}"
) | llm | StrOutputParser()

draft = ChatPromptTemplate.from_template(
    "Write a short follow-up email assigning these action items:\n\n{items}"
) | llm | StrOutputParser()

items = extract.invoke({"transcript": transcript})
if not items.strip():
    raise ValueError("No action items found; not drafting an email.")
email = draft.invoke({"items": items})
```

*Runs two focused calls in sequence, with a plain-code check between them.*

The check between the steps is the part worth copying. Because our code holds the intermediate result, we can validate it, log it, or stop early — something we can't do inside one big prompt that asks for everything at once.

---

## Routing

**Routing** classifies an input and sends it to a specialized handler. The model makes the classification; our code does the dispatch, and there are only as many destinations as we define.

```python
from typing import Literal
from pydantic import BaseModel, Field

class Route(BaseModel):
    destination: Literal["billing", "technical", "general"] = Field(
        description="billing: charges, refunds, invoices. "
                    "technical: errors, outages, how-to. "
                    "general: anything else."
    )

router = llm.with_structured_output(Route)

HANDLERS = {
    "billing": billing_chain,       # each is its own prompt | llm | parser,
    "technical": technical_chain,   # possibly with its own retriever or tools
    "general": general_chain,
}

def handle(question: str) -> str:
    route = router.invoke(
        [("system", "Classify the customer's message."), ("human", question)]
    )
    return HANDLERS[route.destination].invoke({"question": question})
```

*Uses structured output to classify a message, then dispatches it to one of three fixed handlers.*

The `Literal` type is doing real work: the schema limits the model to three valid answers, so the dispatch dict can never be asked for a key it doesn't have. Routing is how we give each category its own prompt, retriever, or even its own model — a small local model for general questions, a stronger one for technical ones — without one prompt trying to be good at everything.

---

## Parallelization

When steps don't depend on each other, run them at once. `RunnableParallel` (the dict form from the RAG notes) executes its branches concurrently:

```python
from langchain_core.runnables import RunnableParallel

review = RunnableParallel(
    security=security_check,     # each branch is its own prompt | llm | parser
    style=style_check,
    tests=test_coverage_check,
)

results = review.invoke({"diff": diff_text})   # {'security': ..., 'style': ..., 'tests': ...}
```

*Runs three independent reviews of the same input concurrently and collects the results in one dict.*

The same structure also supports voting: run one prompt several times and take the majority answer, trading cost for reliability on a high-stakes classification.

---

## Handing Off to Another Agent

Sometimes one step is itself open-ended enough to need an agent. The simplest handoff wraps a specialist agent as a tool that a coordinating agent can call:

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

# search_handbook: a @tool that queries the handbook's Chroma store
# get_order, track_package: the order tools from the What Are AI Agents notes

research_agent = create_agent(
    model=llm,
    tools=[search_handbook],
    system_prompt="Answer HR policy questions from the handbook. Cite the source file.",
)

@tool
def ask_policy_researcher(question: str) -> str:
    """Delegate a question about company HR policy to the policy researcher."""
    result = research_agent.invoke({"messages": [{"role": "user", "content": question}]})
    return result["messages"][-1].content

coordinator = create_agent(
    model=llm,
    tools=[ask_policy_researcher, get_order, track_package],
    system_prompt="You are a general support assistant. Delegate HR policy questions.",
)
```

*Wraps a specialist agent as a tool so the coordinating agent can delegate to it.*

Look at what the specialist sees: a fresh message list containing only the delegated question. It does its own tool calls in its own context, and the coordinator gets back one string. That **context isolation** is the main benefit — the coordinator's history doesn't fill with the specialist's intermediate steps. The costs are nested loops (one coordinator step can trigger several specialist steps) and lost detail (the coordinator only sees the specialist's summary).

This is delegation, where control comes back to the caller. A full **handoff**, where control moves to the other agent and stays there for the rest of the conversation, needs shared state and explicit routing between agents. That's the kind of flow LangGraph is built for.

---

## When a Fixed Pipeline Is Better

Every model call added to a workflow adds latency, cost, and another point of failure. The patterns above are tools for problems we have, not a checklist. A practical order of escalation:

1. **One well-prompted call**, with retrieval if it needs facts. This handles more than people expect.
2. **A fixed chain** when the task naturally splits into steps and each benefits from its own prompt or a check between.
3. **Routing or parallel branches** when inputs fall into distinct categories or have independent parts.
4. **An agent** only when the number or order of steps depends on intermediate results we can't predict.

| Choose a fixed pipeline when... | Choose model-driven steps when... |
|---|---|
| The steps are known in advance | The path depends on what each step finds |
| Inputs are uniform | Inputs vary widely in what they need |
| Latency and cost budgets are tight | Flexibility is worth extra calls |
| We need to audit or test every path | Some variance in behavior is acceptable |

Move up a level only when we can show the simpler version falling short — with a set of test inputs, not a hunch. And a workflow that routes to an agent for one branch is common and sensible: keep the predictable parts fixed, and let the model drive only where it has to.

---

## Key Takeaways

- Workflows connect model calls along paths our code defines; agents choose their own path. Most production systems are workflows, with agents in the branches that need them.
- **Chaining** splits a task into narrow calls, with plain-code checks between them.
- **Routing** uses structured output (a `Literal` field) to classify, then dispatches to a fixed set of handlers.
- **Parallelization** runs independent calls concurrently with `RunnableParallel`, or runs one call several times to vote.
- **Delegating to a sub-agent** by wrapping it as a tool isolates its context; the caller sees only its final answer.
- Start with the simplest structure that works and add steps only when test inputs show you need them.
