# ADR-0004: Liveness scale L0-L4

Status: Accepted (2026-10-02)

**Context**

Design brief §4 and assumption A-05 pin a five-level liveness scale (L0–L4)
reported by `/properties` for any parsed net. The scale must separate three
questions answered per transition: can it fire at all, can it fire from every
reachable state, and do all transitions share each property. The strong
"live" definition follows the MSU course material (D-003, MMSC_VP_03,
Блок 3), under which the in-house ground truth for the smoke net was frozen
(D-009..D-014). This ADR fixes the final wording of the definitions, the
level partition, the classification algorithm, and worked examples that
double as regression fixtures.

**Decision**

Definitions (per transition `t`, over the set `R` of markings reachable from
the initial marking µ0):

- `t` **occurs** iff `t` is enabled at some marking `M ∈ R`.
- `t` is **live** (strong, MSU) iff for every reachable marking `M ∈ R`
  there exists a marking `K` with `M ->* K` (a firing sequence, possibly
  empty) and `t` enabled at `K`.

Algorithm: for each `t`, start from `S_t = { M ∈ R : t enabled at M }` and
compute its backwards closure along reachability edges (a marking joins the
closure when one of its firing successors is already in it). `t` is live iff
the backwards closure covers all of `R`. This is one pass per transition over
the already-built graph: O(|T| · (|R| + |E|)) total, no extra construction.

Level partition for the net (over all of its transitions):

- **L4** — all live;
- **L3** — all occur, not all live;
- **L2** — >=1 live AND >=1 does not occur;
- **L1** — >=1 occurs, none live;
- **L0** — none occur.

Worked examples, each explicitly classified:

1. **Smoke net** (task fixture p1..p6 / t1..t5; D-009..D-012). All five
   transitions occur — each is enabled at some reachable marking. But the net
   has 23 reachable deadlocks (D-011), and at a deadlock no transition is
   enabled; for every `t` there is a reachable `M` (any deadlock) from which
   no `K` with `t` enabled is reachable. Hence no transition is live.
   >=1 occurs, none live → level **L1** (frozen in D-012).
2. **Loop net**: `P = {p1}`, `T = {t1}`, `I(t1) = {p1: 1}`,
   `O(t1) = {p1: 1}`, µ0 = (1,). `R = {(1,)}`; `t1` is enabled at (1,) and
   fires back to (1,). For the only reachable M = (1,) take K = M: the
   strong condition holds. `t1` is live, all live → level **L4**.
3. **Two-place net**: `P = {p1, p2}`, `T = {t1, t2, t3}` with
   `t1: p1 -> p2`, `t2: p2 -> p1`, and `I(t3) = {p1: 1, p2: 1}`,
   `O(t3) = {p1: 1}`, µ0 = (1,0). `R = {(1,0), (0,1)}` — one token shuttles
   between the places. `t1` is live: from (1,0) take K = (1,0), from (0,1)
   take K = (1,0) via `t2`. `t2` is live by the symmetric argument. `t3`
   needs one token on both places simultaneously, impossible while the net
   holds exactly one token: never enabled, does not occur. >=1 live (t1, t2)
   AND >=1 does not occur (t3) → level **L2**.

Unbounded nets (ω-approximation caveat): the level is computed on the
Karp–Miller coverability tree (brief §2) instead of the reachability graph.
At a tree node, `t` is treated as **enabled iff every input weight is
componentwise <= the node's value, with ω treated as dominating any natural**
— a transition whose input place carries ω counts as enabled at that node.
Because the coverability tree over-approximates reachability, "occurs" and
"live" there are approximations: a transition may be judged to occur or be
live because an ω-node covers it without any concrete reachable marking
enabling it. Every report produced in coverability mode carries this caveat;
for bounded nets the classification is exact.

**Consequences**

- Classification is a pure post-pass over the stored graph: deterministic,
  reusable by `/properties` and the JSON report export (brief §7), with no
  additional state to persist.
- The report stores both the net level and the per-transition occurs/live
  flags, so the UI can show the reasoning behind the letter, not just the
  level itself.
- L4 implies deadlock-free; L0 means no transition can ever fire from µ0.
  The smoke net baseline (all occur, none live → L1) and the two toy nets
  above (L4, L2) are the mandatory test fixtures for the liveness function;
  the D-011 deadlock list is the witness that no smoke-net transition is
  live.
- Cost: O(|T|) backwards closures of O(|R| + |E|) each — bounded by
  `REACH_MAX_MARKINGS` (D-020) in bounded mode and by coverability-tree size
  in coverability mode.
