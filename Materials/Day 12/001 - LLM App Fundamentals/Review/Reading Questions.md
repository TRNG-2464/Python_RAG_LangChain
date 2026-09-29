# LLM App Fundamentals — Reading Questions

Use these while reading this unit's notes. They follow the order of the material, so an answer you're hunting for is in the section you're currently reading. Each one points at something worth understanding well enough to explain to a teammate.

---

## Output Parsers

1. A model always returns text. What specific problems does that create when we need the model's answer to feed the next function in our code?

2. Two approaches solve this — prompt-and-parse, and native structured output. What's the practical difference between them, and what would make us pick one over the other?

3. `StrOutputParser` barely does anything, yet we use it constantly. What does it actually do, and what does its role in a chain tell us about how every other parser works?

4. When we write a Pydantic model for extraction, each field gets a `description`. Who reads that text, and what happens to our results if we leave it vague?

5. `PydanticOutputParser` does two separate jobs. What are they, and where does each one happen in the flow of a request?

6. We get a `Person` object back instead of a dict. Name two concrete things that become possible (or safer) because of that.

7. Why is `with_structured_output()` described as more reliable than prompt-and-parse? What is it doing differently?

8. We're running a local model through Ollama and `with_structured_output()` produces garbage. What's the likely cause, and what's the fallback?

9. Why do we wrap a list inside a container model rather than asking the model for a list directly?

10. Validation will catch an `age` that comes back as `"thirty-one"`. What kind of wrong answer will it *not* catch, and why does that matter for anything we build on top of extraction?

11. Setting `temperature=0` is recommended for extraction work. What's the reasoning?

---

## Memory Concepts

12. Models are stateless. Given that, what is "memory" actually made of in an LLM app?

13. In the basic loop, we append the model's reply to the history as well as our own question. What breaks if we only append our questions?

14. In a prompt template, the system message goes first, then history, then the new input. Why does that ordering matter as a conversation gets long?

15. Why does conversation history need a session key, and what goes wrong in a multi-user app without one?

16. What is the context window, and what are the failure modes when a conversation outgrows it? Name more than one.

17. `trim_messages` takes `include_system=True` and `start_on="human"`. What does each one prevent?

18. Trimming and summarization both solve the same problem differently. What does each one cost us, and when would we reach for one over the other?

19. A user's standing preference — say, that they prefer Python over Java — shouldn't live in the conversation history. Where does it belong instead, and why is keeping it in history a bad idea?

---

## Tool Integration

20. When a model "calls a tool," what has actually happened? Be precise about which side executes the code, and explain why that boundary matters.

21. The `@tool` decorator sends three things about our function to the model. What are they, and which one most determines whether the model picks the right tool?

22. We invoke a tool-bound model and get back an empty `.content` with a populated `.tool_calls`. Is something wrong? What is the model waiting for?

23. When we send a tool's result back, we append the `AIMessage` first and include a `tool_call_id`. What is each of those doing, and what breaks without them?

24. What turns a single tool exchange into an agent? And why does that loop need a hard iteration cap — what specifically goes wrong locally without one?

25. When a tool raises an exception, the advice is to return the error to the model as a tool result rather than letting it propagate. What does that buy us?

26. Our `.tool_calls` is consistently empty even on questions that clearly need a tool. What should we check first, and why is the prompt *not* the first suspect?

27. Two tools in our set could plausibly answer the same question. Why is that worse than having ten unrelated tools, and what should we do about it?

28. A tool that can delete records or spend money shouldn't be exposed to a model directly. What protections go around it, and which side makes the final call on what's permitted?
