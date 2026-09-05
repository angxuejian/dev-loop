import json
import os
import sys
import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APITimeoutError, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
review = import_module("code-review")

DIFF = """diff --git a/sample.py b/sample.py
--- a/sample.py
+++ b/sample.py
@@ -1,2 +1,3 @@
 context
-old
+new
+extra
@@ -10 +20 @@
-last
+replacement
"""
COMMENT = {
    "path": "sample.py",
    "start_line": 2,
    "end_line": 3,
    "side": "RIGHT",
    "body": "测试问题",
}


class ReviewTests(unittest.TestCase):
    def test_timeout_configuration(self):
        for value, expected in [("600", 600), ("900", 900)]:
            with (
                patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": value}),
                patch.object(review, "OpenAI") as sdk,
            ):
                sdk.return_value.__enter__.return_value.chat.completions.create.return_value = SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            finish_reason="stop",
                            message=SimpleNamespace(content='{"comments": []}'),
                        )
                    ]
                )
                self.assertEqual(review.review_diff(DIFF, "test-key"), [])
                self.assertEqual(sdk.call_args.kwargs["timeout"], expected)
        for value in ["0", "-1", "nan", "inf", "invalid"]:
            with (
                patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": value}),
                patch.object(review, "OpenAI") as sdk,
            ):
                with self.assertRaises(ValueError):
                    review.review_diff(DIFF, "test-key")
                sdk.assert_not_called()

    def test_timeout_exits_without_posting(self):
        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "PR_NUMBER": "1",
            "GITHUB_TOKEN": "test",
            "PR_HEAD_SHA": "head",
            "LLM_API_KEY": "key",
        }
        with (
            patch.dict(os.environ, env),
            patch.object(review.github_api, "assert_pull_request_head"),
            patch.object(review.github_api, "get_pull_request_diff", return_value=DIFF),
            patch.object(
                review,
                "review_diff",
                side_effect=APITimeoutError(
                    request=httpx.Request("POST", "https://example.com")
                ),
            ),
            patch.object(review.github_api, "create_pull_request_comment") as post,
        ):
            with self.assertRaisesRegex(
                SystemExit, "GLM review timed out; no comments posted"
            ):
                review.main()
            post.assert_not_called()

    def test_incomplete_or_empty_model_response_fails(self):
        for reason, content in [("length", '{"comments": []}'), ("stop", "")]:
            with patch.object(review, "OpenAI") as sdk:
                sdk.return_value.__enter__.return_value.chat.completions.create.return_value = SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            finish_reason=reason,
                            message=SimpleNamespace(content=content),
                        )
                    ]
                )
                with self.assertRaises(ValueError):
                    review.review_diff(DIFF, "test-key")

    def test_sdk_request_and_response(self):
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                str(request.url), "https://api.siliconflow.cn/v1/chat/completions"
            )
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "zai-org/GLM-5.3")
            self.assertIn("PR diff review", body["messages"][0]["content"])
            self.assertIn(DIFF, body["messages"][1]["content"])
            return httpx.Response(
                200,
                json={
                    "id": "test",
                    "created": 0,
                    "model": "zai-org/GLM-5.3",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps({"comments": [COMMENT]}),
                            },
                        }
                    ],
                },
            )

        client = OpenAI(
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        )
        with patch.object(review, "OpenAI", return_value=client):
            self.assertEqual(review.review_diff(DIFF, "test-key"), [COMMENT])

    def test_ranges_and_invalid_outputs(self):
        left = COMMENT | {"side": "LEFT", "end_line": 2}
        self.assertEqual(
            review.validate_comments(json.dumps({"comments": [left]}), DIFF), [left]
        )
        for changes in [
            {"end_line": 20},
            {"path": "missing.py"},
            {"start_line": True},
            {"side": "OTHER"},
            {"body": " "},
            {"token": "injected"},
            {"side": "LEFT", "end_line": 3},
        ]:
            with (
                self.subTest(changes=changes),
                self.assertRaises((ValueError, TypeError)),
            ):
                review.validate_comments(
                    json.dumps({"comments": [COMMENT | changes]}), DIFF
                )
        for content in ["", "```json\n{}\n```", "null", '{"comments": null}']:
            with (
                self.subTest(content=content),
                self.assertRaises((ValueError, TypeError)),
            ):
                review.validate_comments(content, DIFF)
        self.assertEqual(review.validate_comments('{"comments": []}', DIFF), [])
        with self.assertRaises((ValueError, TypeError)):
            review.diff_ranges(DIFF.rstrip().rsplit("\n", 1)[0])

    def test_deleted_and_quoted_paths(self):
        deleted = "diff --git a/a b/a\n--- a/a\n+++ /dev/null\n@@ -4 +0,0 @@\n-x\n"
        self.assertEqual(review.diff_ranges(deleted), [("a", "LEFT", 4, 4)])
        quoted = 'diff --git a/a b/a\n--- "a/a\\tfile"\n+++ "b/a\\tfile"\n@@ -1 +1 @@\n-x\n+y\n'
        self.assertEqual(review.diff_ranges(quoted)[1], ("a\tfile", "RIGHT", 1, 1))

    def test_main_posts_only_findings(self):
        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "PR_NUMBER": "1",
            "GITHUB_TOKEN": "test",
            "PR_HEAD_SHA": "head",
            "LLM_API_KEY": "key",
        }
        for diff, comments, expected in [
            (DIFF, [COMMENT], 1),
            (DIFF, [], 0),
            ("", [], 0),
        ]:
            with (
                self.subTest(expected=expected, diff=bool(diff)),
                patch.dict(os.environ, env),
                patch.object(review.github_api, "assert_pull_request_head"),
                patch.object(
                    review.github_api, "get_pull_request_diff", return_value=diff
                ),
                patch.object(review, "review_diff", return_value=comments) as llm,
                patch.object(
                    review.github_api,
                    "create_pull_request_comment",
                    return_value={"html_url": "test"},
                ) as post,
            ):
                review.main()
                self.assertEqual(post.call_count, expected)
                if not diff:
                    llm.assert_not_called()
                if expected:
                    self.assertEqual(post.call_args.kwargs["commit_id"], "head")
                    self.assertEqual(post.call_args.kwargs["start_line"], 2)

    def test_stale_head_and_invalid_review_never_post(self):
        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "PR_NUMBER": "1",
            "GITHUB_TOKEN": "test",
            "PR_HEAD_SHA": "head",
            "LLM_API_KEY": "key",
        }
        for head_error, review_error in [
            (RuntimeError("stale"), None),
            (None, ValueError("invalid")),
        ]:
            with (
                patch.dict(os.environ, env),
                patch.object(
                    review.github_api,
                    "assert_pull_request_head",
                    side_effect=head_error,
                ),
                patch.object(
                    review.github_api, "get_pull_request_diff", return_value=DIFF
                ),
                patch.object(review, "review_diff", side_effect=review_error),
                patch.object(review.github_api, "create_pull_request_comment") as post,
            ):
                with self.assertRaises((ValueError, RuntimeError)):
                    review.main()
                post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
