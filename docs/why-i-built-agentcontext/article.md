# AI is making it possible to build the tools you need—in a matter of hours.

*How a need for a tiny LLM proxy became AgentContext—and what building it revealed about creating software in the AI era.*

---

As a DevOps/SRE engineer, I started exploring how AI agents could operate in real-world infrastructure—and quickly ran into a practical problem: I couldn't see exactly what they were sending to the LLMs.

My setup spans vendor APIs, self-hosted GPU inference, and GPU servers rented wherever capacity is affordable, while the agents themselves run across Kubernetes clusters. In this kind of environment, regional connectivity becomes a practical concern.

I didn't need another platform managing models, routing, keys, or costs. I needed a tiny, transparent proxy that did one thing: forward traffic to an LLM API.

Once the requests were passing through the proxy, another idea became obvious: why not inspect exactly what was being sent?

What began as a way to inspect API traffic later proved useful with Codex, OpenCode, pi, and other agent clients. So I added request capture and a small timeline UI. That became [AgentContext](https://github.com/rtugov/agentcontext).

I had already explored [Langfuse](https://langfuse.com/) and [LiteLLM](https://docs.litellm.ai/), and later discovered [AgentsView](https://github.com/kenn-io/agentsview) and [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) with its Trajectory view. These projects confirmed that many of us are trying to make agent behavior easier to inspect—but we are approaching the problem from different layers.

AgentContext remained intentionally narrow: observe the live request context at the HTTP boundary without becoming another management platform.

> **This isn't really a story about showing off AgentContext.** What surprised me most was how quickly I could go from “I need this” to a useful first version.

Not long after, I read about [a developer who used Claude Code to make an old Windows-only HP printer work with modern macOS](https://www.tomshardware.com/tech-industry/artificial-intelligence/dev-uses-claude-ai-to-create-native-macos-driver-for-obscure-windows-only-printer-linux-container-hack-enables-system-wide-cmd-p-printing-driver-now-available-on-github). It was a very specific problem, solved because someone needed it solved.

That may be one of the biggest changes in the AI era: software no longer needs to begin with a company, a roadmap, or a large team.

It can begin as a missing personal utility. We can study by building, create something for one narrow problem, and share it when it might help someone else.

## Maybe the most important skill now is noticing friction—and realizing that you can remove it yourself.

---

[Explore the AgentContext demo](https://rtugov.github.io/agentcontext/demo/) · [View the project on GitHub](https://github.com/rtugov/agentcontext)
