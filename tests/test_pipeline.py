"""Unit tests for extraction, classification and scoring. Run: python3 -m unittest discover tests"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))

from extract import to_text, video_ids, context_for
from classify import score_text, is_recommendation
from score import aggregate
from topics import tag
import build_dataset


class ExtractTests(unittest.TestCase):
    def test_hn_html_links(self):
        html = ('Guy Steele:<p><a href="https:&#x2F;&#x2F;www.youtube.com&#x2F;watch?v=_ahvzDzKdB0&amp;t=10" '
                'rel="nofollow">https:&#x2F;&#x2F;www.youtube.com&#x2F;watch?v=_ahvzDzKdB0</a>')
        self.assertEqual(video_ids(to_text(html)), ["_ahvzDzKdB0"])

    def test_url_variants(self):
        t = ("a https://youtu.be/dQw4w9WgXcQ?t=3 b youtube.com/watch?feature=share&v=abcdefghijk "
             "c https://www.youtube.com/embed/ABCDEFGHIJK d https://m.youtube.com/shorts/zyxwvutsrqp "
             "e https://www.youtube-nocookie.com/embed/0123456789a")
        self.assertEqual(video_ids(t), ["dQw4w9WgXcQ", "abcdefghijk", "ABCDEFGHIJK", "zyxwvutsrqp", "0123456789a"])

    def test_no_false_domain(self):
        self.assertEqual(video_ids("notyoutube.com/watch?v=zzzzzzzzzzz"), [])
        self.assertEqual(video_ids("https://www.youtube.com/channel/UCabcdefghijk"), [])

    def test_dedupe_and_order(self):
        t = "https://youtu.be/aaaaaaaaaaa https://youtu.be/bbbbbbbbbbb https://youtu.be/aaaaaaaaaaa"
        self.assertEqual(video_ids(t), ["aaaaaaaaaaa", "bbbbbbbbbbb"])

    def test_context_replaces_urls(self):
        t = "This is a great talk.\n\nhttps://youtu.be/aaaaaaaaaaa"
        c = context_for(t, "aaaaaaaaaaa")
        self.assertIn("great talk", c)
        self.assertNotIn("youtu.be", c)


class ClassifyTests(unittest.TestCase):
    POS = [
        "I highly recommend this talk by Rich Hickey [link]",
        "If you haven't yet seen it, this is an awesome mini-documentary about mission control. [link]",
        "One of the best lectures I've ever watched: [link]",
        "Bret Victor's Inventing on Principle is a must-watch. [link]",
        "Well worth the hour: [link]",
        "I rewatch this talk every year, it changed how I think about software. [link]",
    ]
    NEG = [
        "Source: [link]",
        "[link] for the lazy",
        "I made a video about this a while ago, it's a great explanation: [link]",
        "hahaha the chris rock routine is waaaay better [link]",
        "Does anyone know where the full video is? [link]",
        "This video is misleading and has been debunked many times [link]",
        "Here's the footage of the crash: [link]",
    ]

    def test_positive(self):
        for t in self.POS:
            self.assertTrue(is_recommendation(t), t)

    def test_negative(self):
        for t in self.NEG:
            self.assertFalse(is_recommendation(t), t)

    def test_self_promo_vetoes_even_with_praise(self):
        self.assertFalse(is_recommendation("I highly recommend my own talk: [link]"))

    def test_returns_explanations(self):
        p, pos, neg = score_text("I highly recommend this lecture [link]")
        self.assertGreater(p, 0.9)
        self.assertIn("强烈推荐", pos)

    def test_no_catastrophic_backtracking(self):
        import time
        t = ("word " * 4000) + "?" + (" " * 3000)
        t0 = time.time(); score_text(t)
        self.assertLess(time.time() - t0, 0.5)


def m(author, story, year, p=0.9, rec=True, topics=None, own=False):
    return {"author": author, "story_id": story, "year": year, "p": p, "rec": rec, "topics": topics or [], "own_thread": own}


class ScoreTests(unittest.TestCase):
    def test_one_vote_per_account(self):
        a = aggregate([m("alice", 1, 2010), m("alice", 2, 2015), m("alice", 3, 2020)])
        self.assertEqual(a["recommenders"], 1)

    def test_spread_beats_single_thread(self):
        same_thread = aggregate([m(f"u{i}", 1, 2015) for i in range(5)])
        spread = aggregate([m(f"u{i}", i, 2010 + 3 * i, topics=[f"t{i}"]) for i in range(5)])
        self.assertEqual(same_thread["recommenders"], spread["recommenders"])
        self.assertGreater(spread["score"], same_thread["score"] * 1.5)

    def test_citations_do_not_score(self):
        a = aggregate([m("a", 1, 2010, rec=False), m("b", 2, 2012, rec=False)])
        self.assertEqual(a["score"], 0)
        self.assertEqual(a["citations"], 2)

    def test_own_thread_excluded(self):
        a = aggregate([m("a", 1, 2010, own=True), m("b", 2, 2012)])
        self.assertEqual(a["recommenders"], 1)

    def test_popularity_not_an_input(self):
        base = [m("a", 1, 2010), m("b", 2, 2014)]
        with_views = [dict(x, views=10 ** 9) for x in base]
        self.assertEqual(aggregate(base)["score"], aggregate(with_views)["score"])


class TopicTests(unittest.TestCase):
    def test_word_boundaries(self):
        self.assertNotIn("商业与创业", tag("A network framework (1998)"))
        self.assertIn("编程与软件", tag("JavaScript is the C++ of the Web"))
        self.assertIn("物理与太空", tag("Jeff Bezos Finds Apollo 11 Rockets"))


class BuildTests(unittest.TestCase):
    def test_list_comment_intro_counts(self):
        h = {"objectID": "1", "author": "x", "created_at_i": 1500000000, "story_id": 9, "story_title": "Ask HN: favorite talks?",
             "story_url": None,
             "comment_text": "My all-time favorite talks:<p>Simple Made Easy https://youtu.be/aaaaaaaaaaa"
                             "<p>Inventing on Principle https://youtu.be/bbbbbbbbbbb"}
        ms = build_dataset.mentions_from_comment(h)
        self.assertEqual([x["vid"] for x in ms], ["aaaaaaaaaaa", "bbbbbbbbbbb"])
        self.assertTrue(all(x["rec"] for x in ms))

    def test_own_thread_flag(self):
        h = {"objectID": "2", "author": "y", "created_at_i": 1500000000, "story_id": 9, "story_title": "A video",
             "story_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
             "comment_text": "Great talk https://youtu.be/aaaaaaaaaaa"}
        self.assertTrue(build_dataset.mentions_from_comment(h)[0]["own_thread"])


if __name__ == "__main__":
    unittest.main()
