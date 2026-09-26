"""
test_onboarding_personalization.py - first-visit personalization/onboarding (static/app.jsx):
connecting the ALREADY-EXISTING onboarding interest picker, auth, Follow, Save and homepage
ranking into one coherent guest-and-authenticated personalization flow. No new recommendation
system, no new taxonomy, no new storage layer - this wires up primitives that already existed
(readInterests/writeInterests, followedTopics/followedStories, savedIds, feed_rank, section_rank
story-id lists) rather than building parallel ones.

No JS test runner in this bundler-free project (see test_mobile_share.py/test_contact_form.py
for the same convention) - this inspects the real app.jsx SOURCE for the exact structure the
feature requires, then compiles it with the project's own vendored Babel into a TEMP file (no
_site side effects) as a syntax-validity check.

What this pins (mapped to the 14 required cases):
   1. onboarding interest picks are stored with NO auth gate (guest-safe)
   2. HomeView's "For You" fallback no longer requires auth for the interests signal
   3. toggleInterest mirrors to the account (savePrefsRemote) only when signed in
   4. guest interests migrate to the account on sign-in (onAuthed AND the cold-load restore)
   5. migration is idempotent: the ACCOUNT's own interests win if it already has any; local
      only pushes up when the account has none
   6. toggleFollowTopic still requires auth (guest -> login), for both raw topics and the
      "section:" prefix form
   7. toggleSave still requires auth (guest -> login)
   8. toggleFollowTopic/Story's authenticated branch (follow/unfollow calls) is unchanged
   9. toggleSave's authenticated branch (save/unsave calls) is unchanged
  10. Following (followedTopics/followedStories, explicit) stays a separate signal from
      interests/For You - no code merges onboarding interests into follows_topic
  11. For You is strictly additive (forYou.length>0 && ...), never replaces the lead/major/
      section/brief/gap tiers
  12. no duplicate follows/saves: Formspree-style merge-duplicates upsert on the REST calls,
      and the pending action is cleared immediately after being read (can't replay twice)
  13. returning users don't repeat onboarding: local flag AND a new account-side prefs.onboarded
      flag (for a returning signed-in reader on a brand-new device)
  14. malformed/unavailable local storage fails safe (try/catch -> safe default) for both
      interests and the new pending-action storage

Also pins: the pending-Follow/Save-action replay after sign-in (not one of the numbered 14, but
explicitly required), the account-prompt step (skip is always available, never traps the user),
and that no new dependency / ML system / taxonomy was introduced.

Run:  py test_onboarding_personalization.py
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
FAILURES = []


def check(label, cond):
    print(f"  {label} ... {'OK' if cond else 'FAIL'}")
    if not cond:
        FAILURES.append(label)


src = (ROOT / "static" / "app.jsx").read_text(encoding="utf-8")

print("=== 1/14: onboarding interest picks are guest-safe (no auth gate), fail safe if malformed ===")
check("1a: readInterests/writeInterests exist and are localStorage-backed",
      'const INTERESTS_LS = "paksh-interests";' in src
      and "const readInterests" in src and "const writeInterests" in src)
check("1b: readInterests never throws on malformed JSON - safe [] default",
      re.search(r"const readInterests = \(\) => \{ try\{.*?\}catch\(e\)\{ return \[\]; \}", src) is not None)
tog = re.search(r"const toggleInterest=\(topic\)=>\{.*?\};", src, re.S)
check("1c: toggleInterest exists and does NOT gate on auth (works for guests)",
      tog is not None and "if(!auth)" not in tog.group(0) and "go(\"login\")" not in tog.group(0))
check("1d: toggleInterest still mirrors to the account when signed in",
      tog is not None and "if(auth) savePrefsRemote({ interests:next });" in tog.group(0))

print("\n=== 2: HomeView's onboarding-interest fallback no longer requires auth ===")
hv = re.search(r"function HomeView\(.*?\n(?:.*\n){0,40}", src)
hv_text = hv.group(0) if hv else ""
check("2a: the reading-history path still correctly requires auth (Reading Lens has no guest form)",
      "_fromHistory = !!(auth && lens" in hv_text)
check("2b: the onboarding-interests fallback path is guest-safe (no auth requirement)",
      re.search(r'_topTopics = _fromHistory \? lens\.topics\.slice\(0,4\)\s*\n\s*: \(interests && interests\.length\) \?', hv_text) is not None)
check("2c: the old auth-gated form of the fallback is gone",
      "(auth && interests && interests.length)" not in hv_text)

print("\n=== 4/5: guest->account interest migration exists in BOTH places, and is idempotent ===")
cold_load = re.search(r"loadPrefs\(\)\.then\(p=>\{ if\(!p\) return;(?:.*\n){0,8}", src)
cold_text = cold_load.group(0) if cold_load else ""
check("4a: cold-load restore: account's OWN interests win when it already has some",
      "if(Array.isArray(p.interests) && p.interests.length){ setInterestsState(p.interests); writeInterests(p.interests); }" in cold_text)
check("5a: cold-load restore: local guest picks only migrate up when the account has NONE "
      "(idempotent - a second run finds the account already has interests and stops migrating)",
      "else { const local=readInterests(); if(local.length) savePrefsRemote({ interests:local }); }" in cold_text)
onauthed = re.search(r"const onAuthed=\(s\)=>\{.*?const onSignOut=", src, re.S)
onauthed_text = onauthed.group(0) if onauthed else ""
check("4b: onAuthed (fresh sign-in) does the SAME account-wins / local-migrates-once thing",
      onauthed_text.count("Array.isArray(p.interests)&&p.interests.length") >= 1
      and "savePrefsRemote({ interests:local })" in onauthed_text)

print("\n=== 6/7: guest Follow/Save still require authentication (redirect to the existing login) ===")
def _slice(name_start, name_end):
    i = src.index(name_start)
    j = src.index(name_end, i)
    return type("M", (), {"group": lambda self, _n=0: src[i:j]})()

tsv = _slice("const toggleSave=", "const toggleFollowTopic=")
tft = _slice("const toggleFollowTopic=", "const toggleFollowStory=")
tfs = _slice("const toggleFollowStory=", "\n\n")
check("6a: toggleFollowTopic redirects an unauthenticated attempt to the existing sign-in page",
      tft is not None and 'if(!auth){' in tft.group(0) and 'go("login")' in tft.group(0))
check("6b: this covers BOTH raw topic-follow and section-follow, since section pages call the "
      "SAME toggleFollowTopic with a \"section:\" prefix (no second Follow system)",
      'onToggleFollowTopic("section:"+key)' in src and 'toggleFollowTopic("section:"+_skey)' in src)
check("7a: toggleSave redirects an unauthenticated attempt to the existing sign-in page",
      tsv is not None and 'if(!auth){' in tsv.group(0) and 'go("login")' in tsv.group(0))

print("\n=== 8/9: the AUTHENTICATED branch of Follow/Save is unchanged (same calls) ===")
check("8a: toggleFollowTopic's signed-in path still calls the existing followTopic/unfollowTopic",
      tft is not None and "unfollowTopic(topic)" in tft.group(0) and "followTopic(topic)" in tft.group(0))
check("8b: toggleFollowStory's signed-in path still calls the existing followStory/unfollowStory",
      tfs is not None and "unfollowStory(id)" in tfs.group(0) and "followStory(story)" in tfs.group(0))
check("9a: toggleSave's signed-in path still calls the existing saveStory/unsaveStory",
      tsv is not None and "unsaveStory(id)" in tsv.group(0) and "saveStory(story)" in tsv.group(0))

print("\n=== 10: Following (explicit) stays a separate signal from interests/For You ===")
check("10a: followedTopics/followedStories (explicit Follow) and interests (onboarding/soft "
      "signal) remain two distinct state variables - nothing merges one into the other",
      "setFollowedTopics(new Set())" in src and "setInterestsState(next)" in src
      and not re.search(r"followTopic\(.*interests", src))
check("10b: MyPakshPage's Following lists are still built only from followedTopics/"
      "followedStoryRows, never from onboarding interests",
      "const followedTopicList=Array.from(followedTopics" in src
      and "const followedSectionList=Array.from(followedTopics" in src)

print("\n=== 11: For You is strictly additive - never replaces the arithmetic feed's tiers ===")
check("11a: the lead/major/section/brief tiers are computed independently of forYou "
      "(de-dup'd via the shared `used` set, not gated by personalization)",
      "const lead=cards[0];" in hv_text and "const major=take(cards,1)[0];" in hv_text
      and "const section=take(cards,4);" in hv_text)
check("11b: the For You rail only renders additively (forYou.length>0 &&), the rest of the "
      "page renders unconditionally regardless of whether personalization has any data",
      "{forYou.length>0 && (" in src)

print("\n=== 12: no duplicate follows/saves ===")
check("12a: saved_stories insert uses an upsert (merge-duplicates), not a raw insert that could 409",
      'dbFetch("/saved_stories", { method:"POST", headers:{ Prefer:"resolution=merge-duplicates' in src)
check("12b: follows_topic / follows_story inserts use the same upsert idiom",
      'dbFetch("/follows_topic", { method:"POST", headers:{ Prefer:"resolution=merge-duplicates' in src
      and 'dbFetch("/follows_story", { method:"POST", headers:{ Prefer:"resolution=merge-duplicates' in src)
check("12c: the pending action is cleared the moment it's read, so a re-render/re-mount of "
      "LoginPage or a second onAuthed call can never replay it twice",
      "const pending=readPendingAction(); writePendingAction(null);" in src)

print("\n=== 13: returning users are not repeatedly onboarded ===")
check("13a: the local 'already onboarded' flag still gates the first-run modal",
      'return !localStorage.getItem("paksh-onboarded");' in src)
check("13b: a returning SIGNED-IN reader on a device with no local flag is also recognised, "
      "via the account's own prefs.onboarded - the local flag alone is not the only source",
      "if(p.onboarded){ try{ localStorage.setItem(\"paksh-onboarded\",\"1\"); }catch(e){} setOnboard(false); }" in src)
check("13c: finishOnboarding writes the SAME flag to the account when signed in, so it's "
      "visible on a future device too",
      'const finishOnboarding=()=>{ try{ localStorage.setItem("paksh-onboarded","1"); }catch(e){} setOnboard(false); if(auth) savePrefsRemote({ onboarded:true }); };' in src)

print("\n=== 14: malformed/unavailable local storage fails safe ===")
check("14a: readInterests fails safe (already checked in 1b)", True)
check("14b: the new pending-action reader fails safe on malformed JSON, and rejects a "
      "well-formed-JSON-but-wrong-shape value (no `type`)",
      re.search(r'const readPendingAction = \(\) => \{ try\{ const a=JSON\.parse\(localStorage\.getItem\(PENDING_LS\)\|\|"null"\); return \(a&&typeof a==="object"&&a\.type\)\?a:null; \}catch\(e\)\{ return null; \} \};', src) is not None)

print("\n=== account-prompt step: never traps the user, always skippable ===")
onboarding = re.search(r"function Onboarding\(.*?\n(?:.*\n)*?^    \}\n", src, re.M)
onb_text = onboarding.group(0) if onboarding else ""
check("ob0: Onboarding component found", onboarding is not None)
check("ob1: an already-authenticated visitor's Continue skips the account prompt entirely "
      "(picks interests -> done, no forced auth screen)",
      "const continueFromInterests=()=>{ if(auth){ done(); } else { setShowAcct(true); } };" in onb_text)
check("ob2: the account prompt offers a primary Create-account/Sign-in action that also "
      "navigates to the existing login page",
      "const createAccount=()=>{ done(); go&&go(\"login\"); };" in onb_text)
check("ob3: the account prompt ALWAYS offers a working secondary path that just finishes "
      "onboarding without requiring auth - the user is never trapped",
      re.search(r'<button onClick=\{done\} className=\{`px-5 py-2 text-\[13px\] font-semibold \$\{t\.ts\} hover:\$\{t\.tp\} \$\{isHi\(lang\)\}`\}>\{L\.acctSecondary\}</button>', onb_text) is not None)
check("ob4: the header's own Skip control (identical semantics to Continue-without-account) "
      "is still available at every earlier step",
      onb_text.count("{L.skip}") >= 1)
check("ob5: the SAME 13-section list (SECTION_ORDER) is reused, no new/duplicate taxonomy",
      len(re.findall(r'\["[a-z_]+","[^"]+"\]', src[src.index("const SECTION_ORDER"):src.index("const SECTION_ORDER")+900])) == 13)

print("\n=== no new dependency / ML system introduced ===")
check("dep1: no new npm package.json", not (ROOT / "package.json").exists())
check("dep2: no embeddings/ML/LLM-recommendation terms introduced by this feature",
      not re.search(r"\btensorflow\b|\bembedding_model\b|openai|anthropic\.", src, re.I))

if shutil.which("node"):
    print("\n=== app.jsx still compiles with the project's own Babel (temp file only) ===")
    babel = ROOT / "vendor" / "babel.min.js"
    tmp_out = Path(tempfile.mkdtemp(prefix="paksh_onboarding_test_")) / "app.compiled.js"
    script = (
        "const B=require(process.argv[1]);const fs=require('fs');"
        "const code=B.transform(fs.readFileSync(process.argv[2],'utf8'),{presets:['react'],compact:false}).code;"
        "fs.writeFileSync(process.argv[3],code);"
    )
    try:
        r = subprocess.run(["node", "-e", script, str(babel), str(ROOT / "static" / "app.jsx"), str(tmp_out)],
                            capture_output=True, text=True, timeout=300)
        check("compile: Babel compiles app.jsx without error", r.returncode == 0)
        check("compile: the compiled output contains the new pending-action + account-prompt logic",
              tmp_out.exists() and "paksh-pending-action" in tmp_out.read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(tmp_out.parent, ignore_errors=True)
else:
    print("\n(skipping Babel compile check - node not found on PATH)")

print(f"\n{'=' * 60}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s) failed:")
    for f in FAILURES:
        print(f"  - {f}")
    raise SystemExit(1)
print("ALL ASSERTIONS PASSED")
