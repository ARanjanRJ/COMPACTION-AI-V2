"""Unit tests for the pure compaction logic (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import compactor  # noqa: E402
import config  # noqa: E402
from ollama_client import OllamaError  # noqa: E402


class DedupeTests(unittest.TestCase):
    def test_exact_duplicate_lines_removed(self):
        line = "Please remember that the deadline for the report is the 14th of March."
        out, removed, chars, _ = compactor.dedupe("%s\nsomething else entirely different here ok\n%s" % (line, line))
        self.assertEqual(removed, 1)
        self.assertEqual(out.count("deadline"), 1)
        self.assertGreater(chars, 0)

    def test_duplicate_ignores_case_and_punctuation(self):
        out, removed, _, _ = compactor.dedupe("The server runs on port 8080 always!\nthe server runs on port 8080 always")
        self.assertEqual(removed, 1)

    def test_near_duplicates_are_counted_but_kept(self):
        # one changed word could be a changed fact, so these must NOT be deleted
        base = "the client asked us to confirm that the final report for the quarterly review meeting with the regional managers will be delivered on march"
        a, b = base + " 14", base + " 15"
        out, removed, _, similar = compactor.dedupe(a + "\n" + b)
        self.assertEqual(removed, 0)
        self.assertEqual(similar, 1)
        self.assertIn("march 14", out)
        self.assertIn("march 15", out)

    def test_different_lines_kept(self):
        _, removed, _, _ = compactor.dedupe("The budget is five thousand rupees per month total.\nThe launch date is the first of June next year.")
        self.assertEqual(removed, 0)

    def test_short_lines_always_kept(self):
        out, removed, _, _ = compactor.dedupe("ok\nok\nthanks\nthanks")
        self.assertEqual(removed, 0)
        self.assertEqual(out.count("ok"), 2)

    def test_code_blocks_untouched(self):
        code = "```\nresult = compute_something_long(alpha, beta, gamma)\nresult = compute_something_long(alpha, beta, gamma)\n```"
        out, removed, _, _ = compactor.dedupe(code)
        self.assertEqual(removed, 0)
        self.assertEqual(out.count("compute_something_long"), 2)

    def test_blank_lines_collapsed(self):
        out, _, _, _ = compactor.dedupe("a\n\n\n\n\nb")
        self.assertEqual(out, "a\n\nb")


class ChunkTests(unittest.TestCase):
    def test_chunks_respect_size_and_keep_all_text(self):
        text = "\n".join("line number %d with some words" % i for i in range(200))
        chunks = compactor.chunk_text(text, 300)
        self.assertTrue(all(len(c) <= 300 for c in chunks))
        self.assertEqual("\n".join(chunks).replace("\n", ""), text.replace("\n", ""))
        self.assertGreater(len(chunks), 5)

    def test_single_small_text_is_one_chunk(self):
        self.assertEqual(len(compactor.chunk_text("hello\nworld", 1000)), 1)

    def test_very_long_line_is_split(self):
        chunks = compactor.chunk_text("x" * 1000, 300)
        self.assertEqual([len(c) for c in chunks], [300, 300, 300, 100])


class CheckTests(unittest.TestCase):
    def test_unverified_numbers_flags_invented_figures(self):
        src = "The budget is 5000 and the date is 2026-03-14."
        out = "- budget 5000\n- date 2026-03-14\n- team size 42"
        self.assertEqual(compactor.unverified_numbers(out, src), ["42"])

    def test_list_numbering_not_flagged(self):
        self.assertEqual(compactor.unverified_numbers("10. first item\n11. second", "nothing"), [])

    def test_tidy_output_strips_chatter_and_fences(self):
        raw = "Sure! Here is the summary:\n## PROJECT / TOPIC\n- x"
        self.assertTrue(compactor.tidy_output(raw).startswith("## PROJECT"))
        self.assertEqual(compactor.tidy_output("```markdown\n## KEY FACTS\n- a\n```"), "## KEY FACTS\n- a")

    def test_format_ok(self):
        good = "\n".join("## " + s for s in compactor.SECTIONS)
        self.assertTrue(compactor.format_ok(good))
        self.assertFalse(compactor.format_ok("just a paragraph"))

    def test_prompt_contains_preservation_rules(self):
        p = compactor.system_prompt()
        for needle in ("Never invent", "(unconfirmed)", "CONFLICT", "DATA"):
            self.assertIn(needle, p)

    def test_modes_scale_output_budget(self):
        m = compactor.MODES
        self.assertLess(m["short"]["final_predict"], m["balanced"]["final_predict"])
        self.assertLess(m["balanced"]["final_predict"], m["detailed"]["final_predict"])


def stub_stream(record):
    def fn(model, messages, options):
        record.append((messages, options))
        yield "## PROJECT / TOPIC\n- ok\n"
        yield "## KEY FACTS\n- x"
    return fn


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CHUNK_CHARS", None)
        self.cfg = config.get()

    def test_single_pass(self):
        rec = []
        events = list(compactor.compact("A conversation about a project.\nIt has two lines of text here.", "balanced", "m", self.cfg, stub_stream(rec)))
        self.assertEqual([e["type"] for e in events], ["stage", "result"])
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0][1]["num_predict"], compactor.MODES["balanced"]["final_predict"])
        self.assertEqual(events[-1]["stats"]["chunks"], 1)

    def test_multi_chunk_map_reduce(self):
        self.cfg.chunk_chars = 200
        text = "\n".join("Line %d: we talked about topic number %d in some detail." % (i, i * 7) for i in range(30))
        rec = []
        events = list(compactor.compact(text, "short", "m", self.cfg, stub_stream(rec)))
        n = events[0]["chunks"]
        self.assertGreater(n, 2)
        self.assertEqual(len(rec), n + 1)  # one call per part + one final merge
        self.assertEqual(events[-1]["type"], "result")
        dones = [e["done"] for e in events if e["type"] == "progress"]
        self.assertEqual(dones, sorted(dones))

    def test_hierarchical_merge_when_notes_too_long(self):
        self.cfg.chunk_chars = 150
        self.cfg.merge_chars = 30  # tiny: forces the safety path
        text = "\n".join("Entry %d describes a different subject with its own details." % i for i in range(20))
        events = list(compactor.compact(text, "balanced", "m", self.cfg, stub_stream([])))
        self.assertEqual(events[-1]["type"], "result")
        self.assertTrue(events[-1]["stats"]["merge_truncated"])

    def test_empty_model_answer_is_an_error(self):
        def empty(model, messages, options):
            return iter(())
        with self.assertRaises(OllamaError) as cm:
            list(compactor.compact("Some conversation text that is long enough to process.", "balanced", "m", self.cfg, empty))
        self.assertEqual(cm.exception.code, "empty_response")

    def test_duplicates_are_not_sent_to_the_model(self):
        rec = []
        dup = "This exact sentence is repeated several times in the conversation."
        list(compactor.compact("\n".join([dup] * 5 + ["A different closing line for the chat."]), "balanced", "m", self.cfg, stub_stream(rec)))
        sent = rec[0][0][1]["content"]
        self.assertEqual(sent.count(dup), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
