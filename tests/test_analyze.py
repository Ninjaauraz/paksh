import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# import WITHOUT a key -> analyze.client is None, proving import/unit-test works offline
os.environ.pop("GEMINI_API_KEY", None)
import analyze

# ---- 1) tolerant JSON parser ----
cases = [
    ('```json\n{"a": 1, "b": [1,2,3]}\n```', {"a": 1, "b": [1, 2, 3]}),
    ('{"a": 1, "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),                 # trailing commas
    ('Sure! Here is the JSON:\n{"x": "y"}\nHope that helps.', {"x": "y"}),  # prose-wrapped
    ('{"ok": true}', {"ok": True}),
]
for raw, want in cases:
    got = analyze._extract_json(raw)
    assert got == want, f"parser failed on {raw!r}: got {got}"
print("JSON parser: fences / trailing commas / prose-wrap all recovered ... OK")

# ---- 2) postprocess (full, healthy model output) ----
articles = [
    {"id": 1, "source": "The Hindu",      "language": "en", "title": "EN headline one",
     "url": "https://x/1", "image_url": "https://img/1.jpg", "summary": "s1"},
    {"id": 2, "source": "OpIndia", "language": "en", "title": "EN headline two",
     "url": "https://x/2", "image_url": "",                   "summary": "s2"},
    {"id": 3, "source": "Amar Ujala",     "language": "hi", "title": "हिंदी शीर्षक तीन",
     "url": "https://x/3", "image_url": "",                   "summary": "s3"},
]
raw = {
    "title": "Neutral title", "summary": "One neutral sentence.",
    "summary_points": ["point one", "point two"],
    "title_hi": "तटस्थ शीर्षक", "summary_hi": "एक तटस्थ वाक्य।",
    "summary_points_hi": ["बिंदु एक", "बिंदु दो"],
    "topic": "Politics",
    # per-side framing is now a LIST of bullet points (Ground-News style)
    "framing": {"left": ["left bullet a", "left bullet b"],
                "center": ["center bullet"], "right": ["right bullet"]},
    "framing_hi": {"left": ["वाम बिंदु"], "center": ["केंद्र बिंदु"], "right": ["दक्षिण बिंदु"]},
}
out = analyze.postprocess(raw, articles)
cov = out["coverage"]

# lean comes from sources.py: Hindu=left, OpIndia=right, Amar Ujala=center
assert (cov["left"]["count"], cov["center"]["count"], cov["right"]["count"]) == (1, 1, 1), cov
assert cov["left"]["sources"] == ["The Hindu"] and cov["right"]["sources"] == ["OpIndia"]
# MIN_SIDE_OWNERS=1: each side has exactly one owner, which is now ENOUGH to keep a
# synthesised summary (the one-source-summaries change) - it is no longer silently
# dropped. The UI's own deterministic "sole rated outlet" guardrail (not tested here,
# it lives in app.jsx and reads coverage[side].count===1) is what stops this from
# reading as a whole side's consensus, independent of whatever the model wrote.
assert out["framing"] == raw["framing"], out["framing"]
assert out["framing_hi"] == raw["framing_hi"], out["framing_hi"]
assert out["total_sources"] == 3 and out["degraded"] is False
assert out["image_url"] == "https://img/1.jpg"                 # first article with an image

byname = {s["source"]: s for s in out["sources"]}
assert byname["The Hindu"]["lean"] == "left" and byname["OpIndia"]["lean"] == "right"   # case-insensitive match
assert byname["Amar Ujala"]["lean"] == "center" and byname["Amar Ujala"]["headline"] == "हिंदी शीर्षक तीन"
assert out["title_hi"] == "तटस्थ शीर्षक" and out["summary_points_hi"] == ["बिंदु एक", "बिंदु दो"]
print("postprocess (healthy): coverage from our config, bilingual fields, "
      "per-side framing gated by unique-coverage threshold, hero image ... OK")

# ---- 2b) _clean_framing: list/string normalisation + unique-coverage threshold ----
cov2 = {"left": {"count": 3}, "center": {"count": 1}, "right": {"count": 2}}
cf = analyze._clean_framing(
    {"left": ["a", " b ", "", 5], "center": ["one-owner side, now kept"], "right": "legacy string"},
    cov2)
# MIN_SIDE_OWNERS=1: a one-owner side (center) is now KEPT, not dropped; a zero-owner
# side still would be (tested next).
assert cf == {"left": ["a", "b"], "center": ["one-owner side, now kept"], "right": ["legacy string"]}, cf
cov3 = {"left": {"count": 3}, "center": {"count": 0}, "right": {"count": 2}}
cf3 = analyze._clean_framing({"left": ["a"], "center": ["should be dropped, zero owners"], "right": ["b"]}, cov3)
assert cf3 == {"left": ["a"], "right": ["b"]}, cf3   # zero-owner side still dropped
assert analyze.has_framing(["", "  "]) is False and analyze.has_framing(["x"]) is True
assert analyze.has_framing("") is False and analyze.has_framing("y") is True
print("_clean_framing: bullets kept, one-owner side now kept, zero-owner side still dropped, "
      "legacy string wrapped ... OK")

# ---- 2c) international voting: eligibility comes from a FINAL region, not the reverse ----
# Reuters is a curated INTERNATIONAL-tier outlet with a known underlying lean (center).
assert analyze.lean_of("Reuters") == "international"          # no region passed -> safe default
assert analyze.lean_of("Reuters", "India") == "international"  # India story: never votes
assert analyze.lean_of("Reuters", "World") == "center"         # World story: votes its own lean
# An India-rated outlet's lean never changes with region - only the INTERNATIONAL tier does.
assert analyze.lean_of("The Hindu", "India") == "left" and analyze.lean_of("The Hindu", "World") == "left"
print("lean_of: international outlets vote only on World stories, India-tier outlets unaffected ... OK")

# ---- 2d) postprocess: region is decided from raw classification only, before coverage ----
world_articles = [
    {"id": 1, "source": "Reuters", "language": "en", "title": "Foreign headline",
     "url": "https://x/10", "image_url": "", "summary": "s"},
]
world_raw = {"title": "T", "summary": "S", "region": "World"}
out_world = analyze.postprocess(world_raw, world_articles)
# Reuters now votes CENTRE on this explicitly-World story - not the non-voting "international" tier.
assert out_world["coverage"]["center"]["count"] == 1, out_world["coverage"]
assert out_world["coverage"]["international"]["count"] == 0, out_world["coverage"]
assert out_world["region"] == "World"
india_raw = {"title": "T", "summary": "S", "region": "India"}
out_india = analyze.postprocess(india_raw, world_articles)
# Same outlet, same articles, only the story's OWN region differs -> Reuters stays non-voting.
assert out_india["coverage"]["center"]["count"] == 0, out_india["coverage"]
assert out_india["coverage"]["international"]["count"] == 1, out_india["coverage"]
print("postprocess: voting eligibility follows the story's own region, region never follows "
      "coverage composition ... OK")

# ---- 3) topic validation ----
assert analyze.postprocess({**raw, "topic": "Nonsense"}, articles)["topic"] == "Society"
print("postprocess: invalid topic coerced to 'Society' ... OK")

# ---- 4) graceful degradation (model produced nothing) ----
deg = analyze.postprocess({}, articles)
assert deg["degraded"] is True
assert deg["title"] == "EN headline one"                       # falls back to an article headline
assert (deg["coverage"]["left"]["count"], deg["coverage"]["center"]["count"],
        deg["coverage"]["right"]["count"]) == (1, 1, 1)        # bias bar still works
assert deg["summary"] == "" and deg["summary_points"] == []
print("postprocess (degraded): event still emits bias bar + sources, no fabricated text ... OK")

# ---- 5) PDI optional enrichment contract (final PDI campaign) ----
prompt_no_pdi = analyze.build_prompt(articles)
assert "PUBLIC DISCOURSE" not in prompt_no_pdi
print("build_prompt: with no pdi_context (the default, every pre-existing caller), "
      "output is unchanged - no PDI section appears ... OK")

prompt_with_pdi = analyze.build_prompt(articles, pdi_context="- Some commentators ask whether X will happen.")
assert "PUBLIC DISCOURSE CONTEXT" in prompt_with_pdi
assert "NOT verified Paksh evidence" in prompt_with_pdi
assert "Some commentators ask whether X will happen." in prompt_with_pdi
assert '"title"' in prompt_with_pdi and '"framing"' in prompt_with_pdi   # JSON schema unchanged
print("build_prompt: with a pdi_context, a clearly-labeled supplementary section is appended "
      "without changing the requested JSON schema ... OK")


class _FakePayload:
    """Minimal stand-in for pdi.StoryPDI, just enough to exercise format_payload_for_analyze."""
    def __init__(self, questions=None):
        self.recurring_themes = []
        self.recurring_questions = questions or []
        self.interpretations = []
        self.experiences = []
        self.disagreements = []
        self.uncertainties = []
        self.implications = []
        self.coverage_gaps = []
        self.understanding_contribution = "Public discourse surfaces 1 recurring question(s)."


import pdi as _pdi_mod
empty_text = _pdi_mod.format_payload_for_analyze(_FakePayload())
assert empty_text is None
print("format_payload_for_analyze: an empty StoryPDI (nothing selected) returns None, "
      "not an empty block - PDI says nothing rather than something hollow ... OK")

nonempty_text = _pdi_mod.format_payload_for_analyze(
    _FakePayload(questions=[{"text": "Will the policy actually be enforced?", "recurrence": 2,
                             "source_count": 2, "provider_count": 2}]))
assert nonempty_text is not None and "Will the policy actually be enforced?" in nonempty_text
assert "Understanding contribution:" in nonempty_text
print("format_payload_for_analyze: a genuine question renders a compact, labeled block ... OK")

# analyze_event must never crash even if PDI formatting itself raises - PDI failure must
# never become article-generation failure (Part 1 invariant #19).
class _BrokenPayload:
    pass


result_broken_pdi = analyze.analyze_event(articles, pdi_payload=_BrokenPayload())
assert isinstance(result_broken_pdi, dict) and result_broken_pdi.get("title")
print("analyze_event: a malformed pdi_payload degrades to no-PDI-context rather than raising "
      "(falls through to the same offline extractive path already covered above) ... OK")

# ==========================================================================================
# 2026-09-24 story-quality campaign: evidence-sufficiency gate (compute_evidence_status),
# title-echo detection (is_title_echo), and the _representative()/_extractive_raw() picker
# fix. Fixtures below reproduce two REAL production incidents (event #23887, #23755) -
# no DB dependency, so these run identically in CI and against a fresh checkout.
# ==========================================================================================

# ---- title-echo detection: conservative, must catch RSS artifacts, must not false-positive ----
TITLE = "Is it 'killer robots' or 'super intelligence'? At the UN, leaders see both, AP Explains"
echo_cases = [
    (TITLE, True),                                          # exact
    (TITLE.upper(), True),                                  # case-insensitive
    (TITLE + " apnews.com", True),                           # title + domain
    (TITLE + " AP News", True),                              # title + short outlet name
    (TITLE + " | AP News", True),                            # title + separator + outlet
    (TITLE + " - Source Daily", True),                       # title + dash + outlet
    (TITLE + ".", True),                                     # trailing punctuation only
    (TITLE.replace("'", "’").replace("?", "?"), True),  # curly-quote variant
    ("", False),
    ("Completely unrelated sentence about something else entirely.", False),
]
for summary, want in echo_cases:
    got = analyze.is_title_echo(summary, TITLE)
    assert got == want, f"is_title_echo({summary!r}) = {got}, want {want}"
# A genuine sentence that happens to open with the title text but then adds 30+ chars of
# real substance must NEVER be classified as an echo (this is the "must not false-positive
# on legitimate summaries" requirement - the campaign's #4).
real_continuation = TITLE + ". Officials at the summit spent two days debating a proposed treaty on autonomous weapons systems."
assert not analyze.is_title_echo(real_continuation, TITLE), "a real, substantive continuation must not be flagged as an echo"
# A summary that merely SHARES WORDS with the title (not a prefix match) must never echo.
shares_words = "Leaders at the United Nations discussed killer robots and super intelligence at length today."
assert not analyze.is_title_echo(shares_words, TITLE), "sharing a few title words is not an echo"
print("is_title_echo: exact/case/domain/outlet-suffix/punctuation variants all caught; "
      "real continuations and word-overlap-only summaries never false-positive ... OK")

# ---- _usable_article_text: MIN_USABLE_CHARS floor + echo rejection, but keeps short REAL prose ----
assert analyze._usable_article_text({"title": TITLE, "summary": TITLE + " apnews.com"}) == ""
assert analyze._usable_article_text({"title": TITLE, "summary": "Too short."}) == ""
short_real = "The terminology change follows Trump's UN remarks, while concerns grow."
assert analyze._usable_article_text({"title": TITLE, "summary": short_real}) == short_real
print("_usable_article_text: rejects echoes and near-empty fragments, keeps short-but-real prose ... OK")

# ---- Event #23887 regression fixture (real production article set, 8 articles/6 owners) ----
FIXTURE_23887 = [
    {"id": 645670, "source": "Associated Press", "language": "en",
     "title": "Is it ‘killer robots’ or ‘super intelligence’? At the UN, leaders see both, AP Explains",
     "summary": "Is it ‘killer robots’ or ‘super intelligence’? At the UN, leaders see both, AP Explains apnews.com"},
    {"id": 645827, "source": "The Independent", "language": "en",
     "title": "Senator shreds Trump’s ‘super intelligence’ with edgy two-word retort to AI rebrand",
     "summary": "Democrats scoff at Trump’s attempts to rebrand AI, Eric Garcia writes. It’s a preview to how they will take a more aggressive approach if they win the midterms"},
    {"id": 646687, "source": "The Independent", "language": "en",
     "title": "Senator shreds Trump’s ‘super intelligence’ with edgy two-word retort to his AI rebrand",
     "summary": "Senator shreds Trump’s ‘super intelligence’ with edgy two-word retort to his AI rebrand The Independent"},
    {"id": 647450, "source": "The Pioneer", "language": "en",
     "title": "US diplomats told to use ‘super intelligence’ instead of AI",
     "summary": "US diplomats told to use ‘super intelligence’ instead of AI Pioneer Daily"},
    {"id": 648066, "source": "Firstpost", "language": "en",
     "title": "Trump is rebranding ‘Artificial Intelligence’ as ‘Super Intelligence’. Here’s what will change",
     "summary": "Trump is rebranding ‘Artificial Intelligence’ as ‘Super Intelligence’. Here’s what will change Firstpost"},
    {"id": 648357, "source": "The Hindu BusinessLine", "language": "en",
     "title": "Trump’s ‘super intelligence’ term prompts US State Department to replace ‘AI’ in communications",
     "summary": "The terminology change follows Trump’s UN remarks, while concerns over AI control and calls for global guardrails continue to grow."},
    {"id": 648790, "source": "Business Standard", "language": "en",
     "title": "US diplomats told to use term super intelligence for AI after Trump call", "summary": ""},
    {"id": 648902, "source": "The Pioneer", "language": "en",
     "title": "US diplomats told to use super intelligence instead of AI", "summary": ""},
]
for a in FIXTURE_23887:
    a.setdefault("url", "https://example.com/" + str(a["id"]))
    a.setdefault("image_url", "")

raw_23887 = analyze._extractive_raw(FIXTURE_23887)
assert raw_23887["summary_method"] == "extractive"
assert not analyze.is_title_echo(raw_23887["summary"], raw_23887["title"]), \
    f"event #23887 fixture: picker still chose a title echo: {raw_23887['summary']!r}"
assert "terminology change" in raw_23887["summary"], \
    f"event #23887 fixture: expected the Hindu BusinessLine sentence, got {raw_23887['summary']!r}"
result_23887 = analyze.postprocess(raw_23887, FIXTURE_23887)
assert result_23887["evidence_status"] == analyze.EVIDENCE_PUBLISHABLE, result_23887["evidence_status"]
# And critically: BEFORE the fix, this exact fixture's old-style extractive output (a bare
# title echo) must be caught as NEEDS_REVIEW, not silently accepted - this is what proves
# the GATE (not just the picker) actually closes the hole.
old_style_raw = {"title": FIXTURE_23887[0]["title"],       # AP's own title (the original _representative() pick)
                  "summary": FIXTURE_23887[0]["summary"],  # the AP title-echo, as originally published
                  "summary_method": "extractive"}
status, reason = analyze.compute_evidence_status(
    old_style_raw["summary"], old_style_raw["title"], "extractive", FIXTURE_23887)
assert status == analyze.EVIDENCE_NEEDS_REVIEW, \
    f"the original title-echo summary must be caught as NEEDS_REVIEW, got {status}"
print("event #23887 regression: fixed picker selects the real Hindu BusinessLine sentence, "
      "postprocess() marks it PUBLISHABLE; the ORIGINAL title-echo output is independently "
      "caught as NEEDS_REVIEW by the gate ... OK")

# ---- Event #23755 regression fixture (larger cluster: 18 real articles/13 owners subset of ----
# ---- the actual 42-article/28-owner production cluster, preserving every member that ----
# ---- actually matters to the failure: many title-echo junk sources, several genuinely-empty
# ---- sources, and the real substantive South China Morning Post / Mint sentences) ----
FIXTURE_23755 = [
    {"id": 1, "source": "Sky News", "language": "en",
     "title": "Xi and Trump meeting: What you need to know",
     "summary": "Xi and Trump meeting: What you need to know Sky News"},
    {"id": 2, "source": "DNA (Daily News & Analysis)", "language": "en",
     "title": "Trump-Xi Summit: Trade, Taiwan, Iran, AI and rare earths on agenda| Key points",
     "summary": "Trump-Xi Summit: Trade, Taiwan, Iran, AI and rare earths on agenda| Key points DNA India"},
    {"id": 3, "source": "NPR", "language": "en",
     "title": "From cybersecurity to AI to Taiwan, what's at stake in Trump's summit with Xi",
     "summary": "From cybersecurity to AI to Taiwan, what's at stake in Trump's summit with Xi NPR"},
    {"id": 4, "source": "NBC News", "language": "en",
     "title": "Trump-Xi summit is set to be high in pageantry and low in substance",
     "summary": "Trump-Xi summit is set to be high in pageantry and low in substance NBC News"},
    {"id": 5, "source": "Mint", "language": "en",
     "title": "Donald Trump rolls out red carpet for Xi Jinping as US, China eye deals on trade, AI and rare earths",
     "summary": "On his visit to Washington, Xi Jinping called for US-China cooperation amid trade tensions. He was welcomed with military honors by President Trump."},
    {"id": 6, "source": "NDTV", "language": "en",
     "title": "Team Trump Announces Trade Truce With China As Xi Begins Rare US Visit",
     "summary": "Two superpowers have agreed to scale back tariffs"},
    {"id": 7, "source": "Republic World", "language": "en",
     "title": "Donald Trump Welcomes Xi Jinping in Washington for Three-Day State Visit",
     "summary": "Donald Trump Welcomes Xi Jinping in Washington for Three-Day State Visit Republic World"},
    {"id": 8, "source": "Firstpost", "language": "en",
     "title": "Why did Trump wear gloves and jacket to welcome Xi Jinping? Is the US prez hiding something?",
     "summary": "Why did Trump wear gloves and jacket to welcome Xi Jinping? Is the US prez hiding something? Firstpost"},
    {"id": 9, "source": "National Herald", "language": "en",
     "title": "Trump rolls out lavish red-carpet welcome for Xi as US-China talks begin",
     "summary": "Trump rolls out lavish red-carpet welcome for Xi as US-China talks begin National Herald"},
    {"id": 10, "source": "France 24", "language": "en",
     "title": "Trump gives Xi rare airport welcome as Chinese leader begins US state visit",
     "summary": "US President Donald Trump personally welcomed Chinese President Xi Jinping at a military airfield outside Washington on Wednesday, kicking off a lavish state visit focused on trade, artificial intelligence and Iran."},
    {"id": 11, "source": "South China Morning Post", "language": "en",
     "title": "Big picture or big deals? What the Xi-Trump summit holds for China and the US",
     "summary": "With the balance of power shifting between the US and China, the success of this week’s summit hinges not on headline-grabbing deals, but on practical, cautious consensus under a new strategic stability framework, according to Chinese researchers."},
    {"id": 12, "source": "South China Morning Post", "language": "en",
     "title": "‘Deep respect’: analysts weigh in on Trump’s red carpet welcome for Xi",
     "summary": "With China and the US agreeing to extend a tariff truce that was set to expire in November – and US President Donald Trump giving his Chinese counterpart, Xi Jinping, a personal welcome on the tarmac – analysts say the Chinese leader’s state visit has begun on a positive note."},
    {"id": 13, "source": "South China Morning Post", "language": "en",
     "title": "Xi lands in US for high-stakes summit with Trump amid deep tensions",
     "summary": "Xi lands in US for high-stakes summit with Trump amid deep tensions South China Morning Post"},
    {"id": 14, "source": "The Japan Times", "language": "en",
     "title": "U.S.-China trade truce extended as Xi gets rare welcome from Trump",
     "summary": "U.S.-China trade truce extended as Xi gets rare welcome from Trump japantimes.co.jp"},
    {"id": 15, "source": "Business Standard", "language": "en",
     "title": "China, US should be partners, not rivals, says Xi ahead of talks with Trump", "summary": ""},
    {"id": 16, "source": "The Pioneer", "language": "en",
     "title": "Xi Jinping arrives in Washington, Trump gives rare airport welcome", "summary": ""},
    {"id": 17, "source": "BBC News", "language": "en",
     "title": "Trump offers warm welcome as China Xi arrives for US visit", "summary": ""},
    {"id": 18, "source": "CNBC", "language": "en",
     "title": "U.S.-China trade truce extended for two months, Bessent says, as Xi begins state visit",
     "summary": "U.S.-China trade truce extended for two months, Bessent says, as Xi begins state visit CNBC"},
]
for a in FIXTURE_23755:
    a.setdefault("url", "https://example.com/23755/" + str(a["id"]))
    a.setdefault("image_url", "")

raw_23755 = analyze._extractive_raw(FIXTURE_23755)
assert raw_23755["summary_method"] == "extractive"
assert not analyze.is_title_echo(raw_23755["summary"], raw_23755["title"]), \
    f"event #23755 fixture (18 articles/13 owners): picker still chose a title echo: {raw_23755['summary']!r}"
result_23755 = analyze.postprocess(raw_23755, FIXTURE_23755)
assert result_23755["evidence_status"] == analyze.EVIDENCE_PUBLISHABLE, result_23755["evidence_status"]
print("event #23755 regression (larger cluster, 18 articles/13 owners): fixed picker finds "
      "real substantive text and postprocess() marks it PUBLISHABLE - proves the fix isn't "
      "accidentally dependent on a tiny article set ... OK")

# ---- Genuinely insufficient evidence: NOTHING usable anywhere -> INSUFFICIENT_EVIDENCE, ----
# ---- never silently published (this is the "don't destroy legitimate short stories, but ----
# ---- don't publish nothing either" boundary case) ----
thin_articles = [
    {"id": 901, "source": "Outlet A", "language": "en", "title": "Some event happens in a city",
     "summary": "Some event happens in a city Outlet A", "url": "https://x/901", "image_url": ""},
    {"id": 902, "source": "Outlet B", "language": "en", "title": "Some event happens in a city",
     "summary": "", "url": "https://x/902", "image_url": ""},
]
raw_thin = analyze._extractive_raw(thin_articles)
result_thin = analyze.postprocess(raw_thin, thin_articles)
assert result_thin["evidence_status"] == analyze.EVIDENCE_INSUFFICIENT, result_thin["evidence_status"]
print("genuinely thin cluster (no usable text anywhere) -> INSUFFICIENT_EVIDENCE, not published "
      "as if complete ... OK")

# ---- Legitimate short story: a real, short, self-contained sentence must NOT be rejected ----
# ---- merely for being short (campaign requirement #8: short != incomplete) ----
legit_short = [
    {"id": 903, "source": "Outlet C", "language": "en", "title": "Local team wins regional trophy",
     "summary": "The under-19 team beat their rivals 3-1 in Sunday's final to win the regional trophy.",
     "url": "https://x/903", "image_url": ""},
]
raw_legit = analyze._extractive_raw(legit_short)
result_legit = analyze.postprocess(raw_legit, legit_short)
assert result_legit["evidence_status"] == analyze.EVIDENCE_PUBLISHABLE, result_legit["evidence_status"]
print("legitimate short-but-real single-source story remains PUBLISHABLE - short is not "
      "treated as incomplete ... OK")

# ---- LLM path is PUBLISHABLE regardless of input thinness (synthesis != extraction) -
# AS LONG AS it actually contains real synthesized prose, not just the "llm" tag ----
status, reason = analyze.compute_evidence_status(
    "A real synthesized sentence describing what actually happened in this story.",
    "Some Title", "llm", [])
assert status == analyze.EVIDENCE_PUBLISHABLE and reason == "llm_synthesized"
print("LLM-path summaries with real prose are PUBLISHABLE under the evidence gate "
      "(compute_content_complete already governs their framing-completeness separately) ... OK")

# 2026-09-25 LLM cost campaign: a real benchmark of a SMALLER local model
# (llama3.2:3b) found 8/16 events with summary_method=="llm" but a genuinely EMPTY
# summary field - the "llm" tag alone was never proof of real synthesis, it was a
# shortcut that held for every Gemini sample checked at the time. An empty "llm"
# summary must NOT be blindly trusted - it must fall through to the same
# evidence-sufficiency check any other tier gets.
status, reason = analyze.compute_evidence_status("", "Real headline from the local model", "llm", [])
assert status == analyze.EVIDENCE_INSUFFICIENT, (status, reason)
print("an EMPTY 'llm'-tagged summary (the real llama3.2:3b failure mode) is NOT blindly "
      "trusted - falls through to INSUFFICIENT_EVIDENCE when no better text exists ... OK")

# A title-only ("llm"-tagged) echo must be caught too, not just emptiness.
long_title = "A sufficiently long real-looking headline that would pass the length check alone"
status, reason = analyze.compute_evidence_status(long_title, long_title, "llm", [])
assert status != analyze.EVIDENCE_PUBLISHABLE or reason != "llm_synthesized", (status, reason)
print("a title-ECHO 'llm'-tagged summary is also not blindly trusted via length alone ... OK")

# A genuinely short-but-REAL llm summary must still be PUBLISHABLE (not rejected merely
# for being short) - it falls through to the same "short is not incomplete" rule.
status, reason = analyze.compute_evidence_status("A fire broke out.", "Fire breaks out at plant", "llm", [])
assert status == analyze.EVIDENCE_PUBLISHABLE, (status, reason)
print("a short-but-real (non-echo) 'llm' summary remains PUBLISHABLE - short is still not "
      "treated as incomplete, even under the tightened llm check ... OK")

# Real, verbatim data captured from the actual llama3.2:3b benchmark run (2026-09-25
# LLM cost campaign incident) - not a synthetic string. Both are real production
# event titles that got a genuinely empty summary back from the local model.
for real_title in (
    "AI-powered remake of Willy Wonka's iconic voice actor sparks mixed reviews",
    "ED Arrests Man for Smuggling Gold from Myanmar-UAE, Seizes ₹26 Crore Worth of Go",
):
    status, reason = analyze.compute_evidence_status("", real_title, "llm", [])
    assert status == analyze.EVIDENCE_INSUFFICIENT, (real_title, status, reason)
print("real captured llama3.2:3b empty-summary cases (2 real production titles) are no "
      "longer blindly published ... OK")

# The SAME benchmark run's genuine non-empty llm output (real synthesized prose) must
# still be PUBLISHABLE - the fix must not have collaterally punished a good response.
real_good_summary = ("US President Donald Trump mocked Chinese President Xi Jinping's winter "
                      "attire during a diplomatic exchange, drawing mixed reactions online.")
status, reason = analyze.compute_evidence_status(
    real_good_summary, "Trump Mocks Xi in Unusual Airport Greeting", "llm", [])
assert status == analyze.EVIDENCE_PUBLISHABLE and reason == "llm_synthesized"
print("the SAME benchmark run's genuine non-empty llm output remains PUBLISHABLE "
      "(fix is not collaterally punishing real local-model output) ... OK")

print("\nALL ASSERTIONS PASSED")
