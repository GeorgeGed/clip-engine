"""Each test asserts that one rule in the methodology is actually enforced."""
import sys, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from engine import gates


def frag(**over):
    e = {
        "clip_id": "2026-10-28-tarik-ace-ascent",
        "genre": "frag",
        "source": {"path": "a.mp4", "owner": "tarik", "rights_basis": "explicit", "fps": 60},
        "detection": {"event": "ace", "round_kills": 5},
        "range": {"in": 100.0, "out": 124.0},
        "hook": {"device": "cold_open"},
        "layout": {"mode": "L1"},
        "segments": [{"in": 100.0, "out": 124.0, "speed": 1.0, "in_fight": True}],
        "captions": {"enabled": True, "style": "word", "position_y": 0.64, "max_lines": 2},
        "audio": {"target_lufs": -14.0},
        "tail_frames": 60,
        "qa": {"has_speech": True},
        "render": {"backend": "ffmpeg", "width": 1080, "height": 1920, "fps": 60},
    }
    e.update(copy.deepcopy(over))
    return e


def take(**over):
    e = {
        "clip_id": "2026-10-28-gofns-nrg-roster",
        "genre": "take",
        "source": {"path": "b.mp4", "owner": "gofns", "rights_basis": "explicit", "fps": 60},
        "speaker": {"name": "FNS", "confidence": 0.97, "voices_in_window": 1},
        "claim": {"setup": "s", "claim": "c", "consequence": "q", "contiguous": True},
        "range": {"in": 10.0, "out": 40.0},
        "hook": {"device": "none"},
        "layout": {"mode": "L2", "split_ratio": 0.44, "facecam_detected": True},
        "segments": [{"in": 10.0, "out": 40.0, "speed": 1.0}],
        "captions": {"enabled": True, "style": "phrase", "position_y": 0.55, "max_lines": 2},
        "audio": {"target_lufs": -14.0},
        "tail_frames": 48,
        "qa": {"has_speech": True},
        "render": {"backend": "fcpxml", "width": 1080, "height": 1920, "fps": 60},
    }
    e.update(copy.deepcopy(over))
    return e


def why(res):
    return " | ".join(res.rejected + res.held)


def run():
    fails = []

    def ok(name, cond):
        print(("  pass  " if cond else "  FAIL  ") + name)
        if not cond:
            fails.append(name)

    print("baselines")
    ok("clean frag passes", gates.check(frag()).passed)
    ok("clean take passes", gates.check(take()).passed)
    ok("frag schema-valid", not gates.validate_schema(frag()))
    ok("take schema-valid", not gates.validate_schema(take()))

    print("rights")
    r = gates.check(frag(source={"path": "a.mp4", "owner": "x", "rights_basis": "none", "fps": 60}))
    ok("unpermitted source rejected", not r.passed and "rights_basis" in why(r))
    r = gates.check(frag(inserts=[{"in": 101, "length": 1.0, "asset": "z.jpg"}]))
    ok("insert without rights held", "rights basis" in why(r))

    print("duration")
    ok("4s clip rejected", not gates.check(frag(range={"in": 0, "out": 4})).passed)
    ok("200s clip rejected", not gates.check(frag(range={"in": 0, "out": 200})).passed)
    # The references run 20s and 80s. The clock warns; it does not veto.
    r_ = gates.check(frag(range={"in": 0, "out": 90},
                          segments=[{"in": 0, "out": 90, "speed": 1.0}]))
    ok("90s clip warns, does not reject", r_.passed and any("window" in w for w in r_.warnings))
    r = gates.check(frag(range={"in": 0, "out": 40}, segments=[{"in": 0, "out": 40, "speed": 1.0}]))
    ok("40s frag warns but passes", r.passed and any("frag window" in w for w in r.warnings))

    print("speed discipline")
    two_slow = [
        {"in": 100.0, "out": 100.3, "speed": 0.35},
        {"in": 100.3, "out": 110.0, "speed": 1.0},
        {"in": 110.0, "out": 110.3, "speed": 0.35},
        {"in": 110.3, "out": 124.0, "speed": 1.0},
    ]
    ok("two slow-mos rejected", not gates.check(frag(segments=two_slow)).passed)
    long_slow = [{"in": 100.0, "out": 103.0, "speed": 0.35}, {"in": 103.0, "out": 124.0, "speed": 1.0}]
    r = gates.check(frag(segments=long_slow))
    ok("over-long slow-mo rejected", not r.passed and "source frames" in why(r))
    r = gates.check(frag(segments=[{"in": 100.0, "out": 124.0, "speed": 1.8, "in_fight": True}]))
    ok("sped-up fight rejected", not r.passed and "in_fight" in why(r))
    r = gates.check(frag(segments=[{"in": 100.0, "out": 124.0, "speed": 1.8}]))
    ok("ramp_frames auto-filled", r.passed and any("ramp_frames" in f for f in r.fallbacks))

    print("cut density")
    chop = []
    t = 100.0
    while t < 123.0:
        chop.append({"in": t, "out": t + 1.5, "speed": 1.0})
        t += 2.0
    r = gates.check(frag(segments=chop))
    ok("chopped frag rejected", not r.passed)
    r = gates.check(
        frag(segments=[{"in": 100.0, "out": 110.0, "speed": 1.0}, {"in": 112.0, "out": 124.0, "speed": 1.0}])
    )
    ok("bare hard cut rejected", not r.passed and "bare hard cut" in why(r))
    r = gates.check(
        frag(segments=[
            {"in": 100.0, "out": 110.0, "speed": 1.0},
            {"in": 110.0, "out": 112.0, "speed": 2.0, "ramp_frames": 8},
            {"in": 112.0, "out": 124.0, "speed": 1.0},
        ])
    )
    ok("ramp-covered removal passes", r.passed)

    print("word boundaries")
    wb = [10.0, 15.0, 22.0, 40.0]
    ok("aligned take passes", gates.check(take(), word_boundaries=wb).passed)
    r = gates.check(take(segments=[{"in": 10.0, "out": 23.7, "speed": 1.0}]), word_boundaries=wb)
    ok("mid-word cut rejected", not r.passed and "word boundary" in why(r))

    print("MIN_LINES")
    r = gates.check(take(claim={"setup": "s", "claim": "c", "consequence": "", "contiguous": True}))
    ok("missing consequence rejected", not r.passed and "MIN_LINES" in why(r))
    r = gates.check(take(claim={"setup": "s", "claim": "c", "consequence": "q", "contiguous": False}))
    ok("spliced claim rejected", not r.passed and "non-contiguous" in why(r))

    print("captions")
    r = gates.check(frag(captions={"enabled": True, "style": "word", "position_y": 0.90, "max_lines": 2}))
    ok("caption in bottom exclusion rejected", not r.passed)
    # Measured: R1 uses L2 @ 0.44, R2 uses L2 @ 0.747. Neither may be relocated.
    r = gates.check(take(captions={"enabled": True, "style": "word", "position_y": 0.747, "max_lines": 1}))
    ok("unusual-but-valid caption y preserved", r.edit["captions"]["position_y"] == 0.747)
    r = gates.check(take(captions={"enabled": True, "style": "word", "position_y": 0.44, "max_lines": 1}))
    ok("seam-level caption y preserved", r.edit["captions"]["position_y"] == 0.44)
    r = gates.check(take(captions={"enabled": True, "style": "word", "position_y": 0.55, "max_lines": 2}))
    ok("word captions on take note, not reject", r.passed and any("voice carries" in w for w in r.warnings))
    r = gates.check(
        frag(
            layout={"mode": "L3", "hud_recomposite": [{"element": "killfeed", "src": [0.62, 0.05, 0.38, 0.22], "dst": [0.44, 0.60], "scale": 0.85}]},
            captions={"enabled": True, "style": "word", "position_y": 0.64, "max_lines": 2},
        )
    )
    ok("captions over killfeed rejected", not r.passed and "killfeed" in why(r))
    src = {"path": "a.mp4", "owner": "tarik", "rights_basis": "explicit", "fps": 60, "precaptioned": True}
    r = gates.check(frag(source=src))
    ok("pre-captioned source disables captions", r.edit["captions"]["enabled"] is False)

    print("layout fallbacks")
    r = gates.check(take(layout={"mode": "L2", "split_ratio": 0.44, "facecam_detected": False}))
    ok("no facecam falls back to L1", r.edit["layout"]["mode"] == "L1")
    r = gates.check(
        take(layout={"mode": "L2", "split_ratio": 0.44, "facecam_detected": True, "facecam_frame_fraction": 0.009})
    )
    ok("HUD-sized face falls back to L1", r.edit["layout"]["mode"] == "L1")
    r = gates.check(frag(layout={"mode": "L3"}))
    ok("L3 without recomposite warns", any("killfeed" in w for w in r.warnings))

    print("attribution")
    r = gates.check(take(speaker={"name": "FNS", "confidence": 0.5, "voices_in_window": 1}))
    ok("low confidence held", "confidence" in why(r))
    r = gates.check(take(speaker={"name": "FNS", "confidence": 0.99, "voices_in_window": 2}))
    ok("two voices held", "more than one voice" in why(r))
    r = gates.check(take(speaker={"name": "FNS", "confidence": 0.99, "identified_by_appearance_only": True}))
    ok("appearance-only ID held", "appearance" in why(r))

    print("substance and QA")
    r = gates.check(frag(qa={"has_speech": False}, detection={"event": "none"}))
    ok("empty clip rejected", not r.passed and "nothing happened" in why(r))
    ok("black opening rejected", not gates.check(frag(qa={"has_speech": True, "first_frames_black": True})).passed)
    ok("menu opening rejected", not gates.check(frag(qa={"has_speech": True, "first_frames_menu": True})).passed)
    r = gates.check(frag(audio={"target_lufs": -14.0, "measured_lufs": -22.0}))
    ok("loudness out of range held", "loudness" in why(r))
    ok("bad tail rejected", not gates.check(frag(tail_frames=200)).passed)

    print("measured-reference behaviour")
    receipts = frag(genre="receipts", range={"in": 0, "out": 80.3},
                    segments=[{"in": 0, "out": 80.3, "speed": 1.0}],
                    qa={"has_speech": True, "speech_fraction": 0.50},
                    audio={"target_lufs": -11.79, "measured_lufs": -11.79})
    r = gates.check(receipts)
    ok("80s receipts clip accepted", r.passed)
    ok("-11.79 LUFS accepted", not any("loudness" in h for h in r.held))
    r = gates.check(frag(audio={"target_lufs": -14.0, "measured_lufs": -14.0, "true_peak_dbtp": 1.25}))
    ok("positive true peak held", any("full scale" in h for h in r.held))
    r = gates.check(frag(genre="receipts", range={"in": 0, "out": 80.3},
                         segments=[{"in": 0, "out": 80.3, "speed": 1.0}],
                         qa={"has_speech": True, "speech_fraction": 0.96}))
    ok("receipts with no room for evidence warns", any("evidence" in w for w in r.warnings))
    r = gates.check(take(speaker={"name": "X", "confidence": 0.9, "voices_in_window": 2,
                                  "narrated_intro": True}))
    ok("narrator intro not held", not any("ambiguous" in h for h in r.held))
    r = gates.check(take(speaker={"name": "X", "confidence": 0.9, "voices_in_window": 2}))
    ok("unexplained second voice still held", any("ambiguous" in h for h in r.held))

    print("audio/hook taste")
    r = gates.check(frag(audio={"target_lufs": -14.0, "music": {"bed": "m.wav", "rights_basis": "licensed"}}))
    ok("music on frag warns", any("gunfire" in w for w in r.warnings))
    r = gates.check(frag(hook={"device": "flash_forward", "payoff_in": 120.0}))
    ok("flash_forward length auto-filled", r.edit["hook"]["length_frames"] == 30)
    r = gates.check(frag(hook={"device": "flash_forward"}))
    ok("flash_forward without payoff rejected", not r.passed)

    print()
    print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(run())
