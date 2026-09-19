# How Paksh Rates News — Methodology

*Plain-language version. This page is meant to be public: any reader (or any outlet that disagrees with its rating) can see exactly how Paksh works.*

Paksh shows how the same news story is covered across the political spectrum. To do that, every outlet we track is given a **lean** — Left, Centre, or Right. This page explains how that label is decided.

---

## 1. The most important rule

**Lean describes the *publisher*, not the individual article, and it is never decided by an AI.**

- We rate the **outlet** once, then re-review it periodically. A single news report doesn't get its own lean.
- Software (including AI) helps us *measure* signals at scale — like word choice and which stories an outlet runs. But the **final label is set by people**, using the rubric below, and signed off through a review process.
- The lean you see on a story's bias bar is then just **arithmetic**: we count the outlets covering that story and group them by their publisher lean. No opinion is added per story.

This is the same approach used by established media-bias raters worldwide. It's slower than "let an algorithm decide," but it's the only version that holds up when someone accuses us of bias.

---

## 2. What "Left" and "Right" mean *in India*

In Western media, Left and Right run along one fairly consistent line. India is different — there are at least three separate dimensions, and they don't line up:

- **Social-ideological:** secular / pluralist ←→ Hindu-nationalist (Hindutva)
- **Economic:** welfare / state-led ←→ market / pro-business
- **Institutional:** critical of the current government ←→ aligned with it

An outlet can be pro-market *and* secular; a regional outlet can oppose the central government for purely regional reasons with no ideology involved. Forcing all of this onto one bar loses information.

**So Paksh is explicit about its choice.** The single Left–Centre–Right bar is built mainly from the **social-ideological** and **institutional** dimensions — because that's what Indian readers most associate with "left/right" media. The **economic** dimension is scored and shown *separately* on each outlet's page, so a market-friendly-but-secular outlet isn't mislabeled. We publish the breakdown rather than hiding the judgment inside one number.

"Left" and "Right" are **descriptions, not insults.** Paksh applies the same scrutiny to every outlet, on every side.

---

## 3. The six signals (the rubric)

Each outlet is scored on six signals. Every signal gets a score from **−2 (strongly Left)** to **+2 (strongly Right)**, with **0 = Centre**. The scores are combined using these weights:

| Signal | Weight | What we look at |
|---|---|---|
| Editorial / opinion stance | 30% | The line taken in editorials and op-eds on recurring issues (secularism vs Hindutva framing, treatment of government vs opposition, economic policy, minorities). |
| News framing & language | 25% | Headlines and word choice, what gets foregrounded, whose voices lead the story. *(AI measures this at scale; people validate.)* |
| Story selection / agenda | 20% | What the outlet chooses to amplify vs ignore. This is also the data that powers Blindspots. |
| Sourcing patterns | 10% | Which experts, think-tanks, and politicians the outlet routinely quotes. |
| Ownership & affiliation | 10% | Documented ownership, political/corporate ties, and any declared endorsements (public record). |
| Cross-spectrum blind panel | 5% | A panel with deliberately mixed leanings rates *blinded* samples, to catch single-rater bias. |

The weighted total lands on a scale from **−10 (Left)** to **+10 (Right)**. Anything close to the middle is **Centre**; further out is **Lean** and then **Strong** Left or Right. (See `lean_scoring.py` — the exact, runnable formula.)

---

## 4. How a rating is actually produced

1. **Collect documented facts** about the outlet: ownership, declared positions, and a sample of recent editorials and news stories.
2. **Measure** framing and story-selection signals (software-assisted) across that sample.
3. **Score** each of the six signals from −2 to +2, with a one-line justification per signal.
4. **Run the rubric** to get the composite score and provisional label.
5. **Review:** an editor — and, where possible, the cross-spectrum panel — checks the scores and the rationale against the evidence.
6. **Publish** the lean *with* its rationale, confidence, and last-reviewed date. The outlet can appeal.

---

## 5. Confidence, "contested," and re-review

- **Confidence** (high / medium / low) reflects how complete the evidence is and how much the six signals agree. Low confidence means "we're not sure yet — treat with caution."
- **Contested** marks outlets where reasonable people genuinely disagree about the lean. These are shown with a visible flag rather than presented as settled fact.
- **Re-review** happens on a schedule and immediately after a major change — especially an **ownership change**, which can shift an outlet's framing quickly.

---

## 6. Appeals

Any outlet that believes its rating is wrong can request a review. We re-examine the evidence, and if the rating stands we publish the reasoning. Disagreements are handled in the open.

---

## 7. v1 status — please read

The ratings shipping in this first version are **provisional drafts**. They reflect *commonly-documented positioning* and are a starting point — **not** Paksh's final word. Several are explicitly marked *contested*. Before public launch, every rating is reviewed against sources and, ideally, the cross-spectrum panel. We would rather mark an outlet **Unrated** than guess.

---

## 8. A note on reading Paksh

Paksh is built for a wide Indian audience, much of which hasn't used a "media bias" tool before. So:

- The bias bar and colours do most of the work — you shouldn't need to read much to get the point.
- Every label can be tapped for a plain-language explanation of *why*.
- Paksh works in **English and Hindi** (more languages to come), because seeing every side only matters if it's in a language you read comfortably.

The goal isn't to tell you what to think. It's to show you what you might be missing.

## 9. How stories, the bias bar and Coverage Gaps are computed

Section 1-8 explain how an *outlet* is rated. This section explains what Paksh does with those
ratings. Everything here is arithmetic or a stated rule; where an AI model is used, it is named.

**Where AI is used (and where it is not).** A language-embedding model groups articles about the
same happening into one *event*. A language model writes the neutral summary and the per-side
framing text, in English and Hindi. **No AI decides an outlet's lean, the bias bar, or whether
something is a Coverage Gap.** Lean labels come only from the editorial roster in section 3-4.

**The bias bar.** For each event Paksh counts *distinct outlet owners* on each side (Left, Centre,
Right). One vote per owner: co-owned mastheads count once, and a second article from the same
outlet adds nothing. International wires and unrated outlets are shown but never vote.

**A Coverage Gap.** An event is flagged when it is lopsided between Left and Right:
(Left owners + Right owners) is at least 4, **and** the smaller of the two is at most 25% of the
larger. Centre, international and unrated outlets never enter this test. Gaps are ranked by
(Left - Right)^2 / (Left + Right), lightly favouring recent stories (the weight halves every
72 hours), and the Coverage Gaps page lists every qualifying event in both directions.

**What a Coverage Gap does *not* say.** It is a count of who covered a story, not a judgement
about why. A story can be under-covered by one side because it is local, because it broke recently,
or because it is of little interest to that side. Paksh does not infer motive or claim bias.

**Developing stories.** Two events are linked into one storyline only when they share a topic, fall
within a rolling window of days, are semantically close (embedding similarity at or above a fixed
threshold), *and* share several distinguishing words in their headlines. Chains that grow too large
are discarded as topic drift rather than published as a false thread. A storyline is chronology; it
never changes any event's bias bar.

**Summaries and framing.** The summary uses only facts present in the coverage given to the model:
it separates fact, allegation, claim and disputed claim, names no publication, and states only what
the supplied reporting supports (it is told not to add background or consequences of its own). The
per-side framing describes what each side emphasises *relative to the others*, and says so plainly
when a side simply repeats the shared facts.

**Known limits.** Summaries can be thin when outlets supply little text beyond a headline; the
model sees short excerpts, not full articles. Editorial ratings, though rubric-based, involve
judgement (section 5-6 describe review and appeals).
