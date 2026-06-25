"""
calibrate.py - find good clustering thresholds for your LOCAL embedder.

Why: cluster.py's thresholds depend on the embedding model. bge-m3's cosine scale
runs lower than Gemini's, so the right JOIN / HIGH / STRONG numbers differ. This
script embeds a handful of REAL headlines (some report the same event, some don't)
through whatever backend cluster.py is set to, measures how far apart "same story"
and "different story" sit, and prints the threshold lines to paste into cluster.py.

Run it once after `ollama pull bge-m3`:   py calibrate.py
It needs Ollama running; it does NOT touch your database.
"""

import numpy as np
import cluster

# Labelled sample pulled from a real Paksh ingest. (story, language, headline)
SAMPLE = [
    ("tmc_merger", "en", "Trinamool Rebel Bloc To Merge With Nationalist Citizens Party: Kakoli Ghosh"),
    ("tmc_merger", "en", "Rebel TMC MPs To Merge With Nationalist Citizens Party & Support BJP-Led NDA"),
    ("tmc_merger", "en", "Rebel TMC MP faction merges with Nationalist Citizens Party of India"),
    ("tmc_merger", "hi", "TMC के 20 बागी सांसद नेशनलिस्ट सिटीजन्स पार्टी में करेंगे विलय, NDA को देंगे समर्थन"),
    ("tmc_merger", "hi", "TMC Split: किस पार्टी में शामिल होंगे TMC के बागी? काकोली का एलान"),
    ("an32_crash", "en", "Indian Air Force AN-32 Transport Plane Crashes While Landing At Jorhat Air Base"),
    ("an32_crash", "en", "IAF aircraft AN-32 crashes while landing in Assam's Jorhat"),
    ("an32_crash", "en", "5 Indian Air Force Personnel Killed as AN-32 Aircraft Crashes in Assam's Jorhat"),
    ("an32_crash", "hi", "असम में इंडियन एयरफोर्स का प्लेन क्रैश, 5 जवान शहीद"),
    ("gold_rate",  "en", "Gold, silver rates today: Comex gold rebounds"),
    ("spacex_ipo", "en", "SpaceX shares rise 11% on Nasdaq debut, market cap just shy of $2 trillion"),
    ("horoscope",  "en", "Horoscope today: Astrological predictions for June 15, 2026"),
]


def _pct(xs, p):
    return float(np.percentile(np.array(xs), p)) if xs else float("nan")


def main():
    print("\nEmbedding %d sample headlines via backend=%s (model: %s) ...\n"
          % (len(SAMPLE), cluster.BACKEND.upper(), cluster.EMBED_MODEL))
    try:
        raw = cluster._raw_embedder()           # active backend, uncached -> hits Ollama
        vecs = cluster._normalize(raw([h for _, _, h in SAMPLE]))
    except RuntimeError as e:
        print(str(e) + "\n")
        return

    same_lang_same_story, cross_lang_same_story, different_story = [], [], []
    n = len(SAMPLE)
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(np.dot(vecs[i], vecs[j]))
            (si, li, _), (sj, lj, _) = SAMPLE[i], SAMPLE[j]
            if si == sj:
                (same_lang_same_story if li == lj else cross_lang_same_story).append(sim)
            else:
                different_story.append(sim)

    print("Cosine similarity between headline pairs:")
    print("  SAME story, same language : min %.3f  median %.3f  max %.3f"
          % (min(same_lang_same_story), _pct(same_lang_same_story, 50), max(same_lang_same_story)))
    if cross_lang_same_story:
        print("  SAME story, EN<->HI       : min %.3f  median %.3f  max %.3f"
              % (min(cross_lang_same_story), _pct(cross_lang_same_story, 50), max(cross_lang_same_story)))
    print("  DIFFERENT stories         : min %.3f  median %.3f  max %.3f"
          % (min(different_story), _pct(different_story, 50), max(different_story)))

    weakest_true = min(same_lang_same_story)
    strongest_false = max(different_story)
    margin = weakest_true - strongest_false
    print("\nSeparation margin (weakest real pair - strongest false pair): %.3f" % margin)
    if margin <= 0:
        print("  !! Overlap: real and unrelated pairs aren't cleanly separable on this"
              "\n     sample. The keyword gate still protects you, but expect some misses.")

    # Recommend: JOIN just under the weakest true same-language pair, but safely above
    # the strongest unrelated pair. STRONG ~ median true. HIGH (cross-lingual trust)
    # just under the weakest EN<->HI true pair. MERGE a touch above JOIN.
    floor = strongest_false + 0.02
    join = round(max(min(weakest_true - 0.03, _pct(same_lang_same_story, 10)), floor), 2)
    strong = round(max(_pct(same_lang_same_story, 50), join + 0.05), 2)
    if cross_lang_same_story:
        high = round(max(min(cross_lang_same_story) - 0.02, floor, strong), 2)
    else:
        high = round(max(strong, 0.80), 2)
    merge = round(join + 0.03, 2)

    print("\n" + "=" * 64)
    print("Recommended thresholds for %s. Paste into the `else:` (ollama)" % cluster.EMBED_MODEL)
    print("block near the top of cluster.py:")
    print("=" * 64)
    print("    JOIN_THRESHOLD = %.2f" % join)
    print("    MERGE_THRESHOLD= %.2f" % merge)
    print("    HIGH_SIM       = %.2f" % high)
    print("    STRONG_SIM     = %.2f" % strong)
    print("    DUP_THRESHOLD  = 0.90")
    print("=" * 64)
    print("Then re-run:  py cluster.py   (real events should appear, marked *)\n")


if __name__ == "__main__":
    main()