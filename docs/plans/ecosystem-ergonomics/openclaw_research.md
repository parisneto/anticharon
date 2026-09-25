## Conclusion

For **OpenClaw**, I would keep Anticharon's two-tier philosophy but change Tier 2 substantially:

> **Tier 1:** trust OpenClaw's own JSON introspection.
> **Tier 2:** use a tiny **JSON5-aware streaming lexer**, not Hermes-style indentation parsing.
> **Safety:** any ambiguity in config ownership, agent scope, alias resolution, includes, or structure sets `incomplete=True`; Anticharon keeps the previous valid shortlist.

This maps unusually well to OpenClaw because it already exposes machine-readable model state through its CLI.

As of **September 24, 2026**, the relevant OpenClaw model order is:

```text
agents.defaults.model.primary
        ↓
agents.defaults.model.fallbacks[0]
        ↓
agents.defaults.model.fallbacks[1]
        ↓
...
```

Authentication-profile rotation happens **inside a provider before OpenClaw moves to the next model fallback**, so Anticharon does not need to treat auth profiles as additional pricing models. ([GitHub][1])

---

# 1. How OpenClaw stores this today

The normal config is JSON5:

```text
~/.openclaw/openclaw.json
```

or:

```text
$OPENCLAW_STATE_DIR/openclaw.json
```

with `OPENCLAW_CONFIG_PATH` taking explicit precedence. ([GitHub][2])

A normal model configuration looks like:

```json5
{
  agents: {
    defaults: {
      model: {
        primary: "openrouter/openai/gpt-5.6-luna",
        fallbacks: [
          "openrouter/deepseek/deepseek-v4-flash-0731",
          "openrouter/qwen/qwen3.7-flash",
        ],
      },
    },
  },
}
```

OpenClaw explicitly supports both:

```json5
model: "openrouter/openai/gpt-5.6-luna"
```

and:

```json5
model: {
  primary: "...",
  fallbacks: ["...", "..."],
}
```

The fallback array is ordered. ([OpenClaw][3])

### Important difference from Hermes

Hermes separates these:

```yaml
provider: openrouter
model: openai/gpt-5.6-luna
```

OpenClaw encodes the provider into the model ref:

```text
openrouter/openai/gpt-5.6-luna
^^^^^^^^^^ ^^^^^^^^^^^^^^^^^^^^
provider   OpenRouter model slug
```

OpenClaw splits model references on the **first `/`**. Its documentation explicitly uses OpenRouter refs such as:

```text
openrouter/moonshotai/kimi-k2
```

([GitHub][1])

So Anticharon's normalization becomes beautifully simple:

```python
provider, model_slug = ref.split("/", 1)
```

For:

```text
openrouter/openai/gpt-5.6-luna
```

you get:

```text
provider   = openrouter
model_slug = openai/gpt-5.6-luna
```

which is exactly the OpenRouter pricing slug Anticharon wants.

---

# 2. Recommended OpenClaw dual-tier adapter

## Tier 1 — native CLI introspection

For the **effective configured route**, I would make this the primary command:

```bash
openclaw models status --json
```

or when Anticharon knows which agent it is inspecting:

```bash
openclaw models status --agent main --json
```

`models status` reports the resolved default and fallbacks, and `--json` keeps stdout machine-readable. It does **not** make a model request unless `--probe` is explicitly supplied. ([OpenClaw][4])

Current OpenClaw JSON output exposes fields such as:

```json
{
  "defaultModel": "openai/gpt-5.6-sol",
  "resolvedDefault": "openai/gpt-5.6-sol",
  "fallbacks": [
    "openai/gpt-5.6-terra",
    "openai/gpt-5.5"
  ]
}
```

Real current OpenClaw reports demonstrate this shape. ([GitHub][5])

I would therefore extract:

```python
primary = payload["resolvedDefault"]
fallbacks = payload.get("fallbacks", [])
```

and then:

```python
chain = stable_dedupe([primary, *fallbacks])
```

That dedupe matches OpenClaw's own fallback semantics: explicitly configured fallbacks are deduplicated while preserving operator intent/order. ([OpenClaw][6])

### Secondary native CLI route

If `models status --json` is unavailable on an older OpenClaw release:

```bash
openclaw config get agents.defaults.model --json
```

OpenClaw explicitly documents that command and emits the config value as JSON. ([GitHub][7])

Then handle:

```json
"openrouter/openai/gpt-5.6-luna"
```

as:

```python
primary = value
fallbacks = []
```

or:

```json
{
  "primary": "openrouter/openai/gpt-5.6-luna",
  "fallbacks": [...]
}
```

normally.

I would keep Anticharon's `subprocess.run(..., timeout=2.0)` policy configurable but start at the same **2 seconds**, no shell invocation:

```python
subprocess.run(
    ["openclaw", "models", "status", "--json", ...],
    capture_output=True,
    text=True,
    timeout=2.0,
    check=False,
)
```

---

# 3. Multi-agent handling matters

OpenClaw supports:

```json5
agents: {
  defaults: {
    model: {...}
  },

  entries: {
    main: {
      model: {...}
    },

    research: {
      model: {...}
    }
  }
}
```

A per-agent model overrides the default. A per-agent string is strict; a per-agent object can have its own fallback chain. ([OpenClaw][8])

Therefore I would explicitly distinguish:

```text
scope = global-default
```

from:

```text
scope = effective-agent:main
```

For Anticharon integration with an actual running OpenClaw agent, I would prefer:

```bash
openclaw models status --agent <agent-id> --json
```

rather than blindly reading `agents.defaults.model`.

One subtlety: this still represents the **configured agent route**, not a temporary model selected inside a particular chat session. OpenClaw documents that `models status` does not inspect session overrides. ([OpenClaw][4])

For Anticharon's persistent shortlist, that is probably the correct semantic boundary.

---

# 4. Tier 2 — raw file extraction

This should **not** copy the Hermes YAML parser.

OpenClaw's config is JSON5, so indentation has no semantic value. This is valid:

```json5
{
  agents: { defaults: { model: {
    primary: 'openrouter/openai/gpt-5.6-luna',
    fallbacks: ['openrouter/qwen/qwen3.7-flash'],
  }}}
}
```

Therefore Tier 2 should be a small streaming lexical scanner.

It needs only enough JSON5 awareness to recognize:

```text
{
}
[
]
:
,
quoted strings: "..." and '...'
unquoted object keys
// comments
/* comments */
```

while maintaining:

```python
object_path
brace_depth
array_depth
quote_state
escape_state
block_comment_state
```

It does **not** need to become a general JSON5 implementation.

The targeted paths are only:

```text
agents.defaults.model
agents.defaults.model.primary
agents.defaults.model.fallbacks

agents.entries.<agent-id>.model
agents.entries.<agent-id>.model.primary
agents.entries.<agent-id>.model.fallbacks
```

Inline and multiline fallback arrays should both work.

That is important because unlike Hermes YAML, this:

```json5
fallbacks: ["a", "b", "c"]
```

is perfectly ordinary OpenClaw configuration and should **not** by itself trigger `incomplete`.

---

# 5. The OpenClaw-specific `incomplete` lock

I would return something like:

```python
ExtractionResult(
    primary: str | None,
    fallbacks: tuple[str, ...],
    shortlist: tuple[str, ...],
    source: str,
    scope: str,
    incomplete: bool,
    incomplete_reasons: tuple[str, ...],
)
```

And make completeness affirmative rather than optimistic:

```python
complete = (
    structure_complete
    and scope_complete
    and refs_complete
    and ownership_complete
    and read_consistent
)
```

### Conditions that set `incomplete=True`

For OpenClaw specifically:

| Situation                                                                       | Result                 |
| ------------------------------------------------------------------------------- | ---------------------- |
| CLI timeout / non-zero / invalid JSON                                           | Fall through to Tier 2 |
| Missing/invalid primary                                                         | incomplete             |
| `fallbacks` exists but is not an array of strings                               | incomplete             |
| Unterminated quote/comment/array/object                                         | incomplete             |
| Relevant duplicate `model`, `primary`, or `fallbacks` keys                      | incomplete             |
| File changes while being streamed                                               | incomplete             |
| Effective-agent extraction requested but agent cannot be determined             | incomplete             |
| Relevant per-agent model override exists but parser extracted only defaults     | incomplete             |
| Legacy `agents.list[...]` structure encountered and parser doesn't support it   | incomplete             |
| Model ref requires provider inference/alias resolution that Tier 2 cannot prove | incomplete             |
| `${...}` occurs in a model ref and cannot be safely resolved                    | incomplete             |
| `$include` can affect the relevant model subtree                                | incomplete             |

That final case is especially important.

OpenClaw officially supports:

```json5
{
  agents: {
    $include: "./agents.json5"
  }
}
```

plus include arrays, nested includes up to 10 levels, ordered deep-merging, and sibling overrides. ([OpenClaw][9])

I would **not reimplement this in Anticharon v1**.

If Tier 1 failed and the raw scanner sees:

```text
$include
```

at the root or anywhere capable of affecting:

```text
agents
agents.defaults
agents.entries
```

then:

```python
incomplete = True
reason = "relevant_openclaw_include"
```

and the existing shortlist survives unchanged.

An unrelated:

```json5
plugins: {
  $include: "./plugins.json5"
}
```

doesn't need to poison model extraction.

---

# 6. Alias/provider ambiguity

OpenClaw also supports aliases and provider inference. It can resolve an unqualified model by checking aliases, configured providers, and finally a deprecated default-provider fallback. ([GitHub][1])

So if raw Tier 2 finds:

```json5
primary: "opus"
```

Anticharon must **not** guess:

```text
provider = anthropic
```

Likewise:

```json5
primary: "gpt-5.6-sol"
```

does not give enough information to prove OpenRouter versus OpenAI.

The rule should be:

```python
if "/" not in resolved_ref:
    incomplete = True
```

unless Tier 2 has also conclusively parsed and resolved the relevant OpenClaw alias mapping.

Tier 1 largely removes this problem because OpenClaw itself performs the resolution.

---

# 7. Provider filtering

Once refs are fully resolved:

```python
def openclaw_target_slug(ref: str, target_provider: str) -> str | None:
    provider, model = ref.split("/", 1)

    if provider.lower() != target_provider.lower():
        return None

    return model
```

Example:

```text
chain:
  openrouter/openai/gpt-5.6-luna
  anthropic/claude-sonnet-5
  openrouter/deepseek/deepseek-v4-flash-0731
```

produces:

```text
OpenRouter shortlist:
  openai/gpt-5.6-luna
  deepseek/deepseek-v4-flash-0731
```

The Anthropic fallback is not an error. It is simply outside Anticharon's OpenRouter pricing universe.

A completely extracted route containing **zero OpenRouter models** is therefore a valid, authoritative empty result. That is different from a parser that failed before discovering all fallbacks.

---

# 8. Exact write-safety rule

I would preserve Anticharon's existing principle but make the commit boundary explicit:

```python
result = extract_openclaw()

if result.incomplete:
    return KEEP_EXISTING_SHORTLIST

candidate = validate_and_normalize(result)

write(candidate, temporary_path)
flush_and_fsync(temporary_path)
os.replace(temporary_path, shortlist_path)
```

`os.replace()` gives you an atomic filesystem replacement with only Python stdlib.

I would also stat the OpenClaw config before and after Tier-2 parsing:

```python
before = os.stat(path)

parse_stream(...)

after = os.stat(path)

if (
    before.st_ino != after.st_ino
    or before.st_size != after.st_size
    or before.st_mtime_ns != after.st_mtime_ns
):
    incomplete = True
    incomplete_reasons.append("config_changed_during_read")
```

So a hot OpenClaw config rewrite cannot produce a half-old/half-new Anticharon shortlist.

And because OpenClaw itself requires its active config path to be a regular file and warns against symlinked config layouts, I would reject a symlink at Tier 2 rather than silently following it. ([GitHub][10])

---

# 9. What the wider ecosystem suggests

The broader research strongly supports this adapter architecture.

**LiteLLM** is declarative but substantially more complicated than Hermes/OpenClaw: its YAML can contain multiple deployments for one model group, routing strategies, retries, cooldowns and model-group fallbacks. A "fallback" may therefore refer to another routing group rather than directly to a concrete provider/model. ([LiteLLM][11])

**OpenHands** goes further: its current SDK can configure a `FallbackStrategy` in Python, with fallback names referring to models persisted in an `LLMProfileStore` under `.openhands/profiles`. Its routing may literally be runtime application code rather than one static config tree. ([OpenHands Docs][12])

That suggests a good general Anticharon contract:

```text
native machine-readable introspection
        ↓
declarative config extraction
        ↓
conservative partial parser
        ↓
INCOMPLETE → preserve old state
```

rather than trying to build one "universal config parser."

## Recommended OpenClaw adapter

So the concrete architecture I would implement is:

```text
OpenClawAdapter
│
├─ Tier 1A
│   openclaw models status [--agent ID] --json
│   → effective configured route
│
├─ Tier 1B
│   openclaw config get agents.defaults.model --json
│   → authored global fallback
│
└─ Tier 2
    active openclaw.json
    → zero-dependency JSON5 lexical scanner
    → targeted model paths only
    → fail closed on scope/include/alias ambiguity

normalize:
    [primary, *fallbacks]
       ↓ stable dedupe
       ↓ provider == "openrouter"
       ↓ strip first "openrouter/"
       ↓ Anticharon pricing shortlist

commit:
    only if incomplete == False
    otherwise preserve previous valid shortlist
```

The key design change from Hermes is therefore **not** the two-tier architecture—it survives very well. It is that OpenClaw Tier 2 must be **brace/token-aware and scope-aware**, rather than indentation-aware.

[1]: https://github.com/openclaw/openclaw/blob/main/docs/concepts/models.md "openclaw/docs/concepts/models.md at main · openclaw/openclaw · GitHub"
[2]: https://github.com/openclaw/openclaw/blob/main/src/config/paths.ts?utm_source=chatgpt.com "openclaw/src/config/paths.ts at main · openclaw/openclaw · GitHub"
[3]: https://docs.openclaw.ai/gateway/config-agents/models "Configuration — agent models - OpenClaw"
[4]: https://docs.openclaw.ai/cli/models "Models - OpenClaw"
[5]: https://github.com/openclaw/openclaw/issues/66872?utm_source=chatgpt.com "[Bug]: models status --json reports missingProvidersInUse: [\"codex\"] for Codex harness models even when native Codex auth exists · Issue #66872 · openclaw/openclaw · GitHub"
[6]: https://docs.openclaw.ai/concepts/model-failover "Model failover - OpenClaw"
[7]: https://github.com/openclaw/openclaw/blob/main/docs/cli/config.md "openclaw/docs/cli/config.md at main · openclaw/openclaw · GitHub"
[8]: https://docs.openclaw.ai/gateway/config-agents/entries-and-multi-agent "Configuration — per-agent entries and multi-agent routing - OpenClaw"
[9]: https://docs.openclaw.ai/gateway/config-secrets-env "Configuration — environment, secrets, and includes - OpenClaw"
[10]: https://github.com/openclaw/openclaw/blob/main/docs/gateway/configuration.md "openclaw/docs/gateway/configuration.md at main · openclaw/openclaw · GitHub"
[11]: https://docs.litellm.ai/docs/routing?utm_source=chatgpt.com "Router - Load Balancing | liteLLM"
[12]: https://docs.openhands.dev/sdk/guides/llm-fallback "LLM Fallback Strategy - OpenHands Docs"
