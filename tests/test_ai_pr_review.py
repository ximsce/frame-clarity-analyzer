import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / ".github" / "scripts" / "ai_pr_review.py"
SPEC = importlib.util.spec_from_file_location("ai_pr_review", SCRIPT_PATH)
ai_pr_review = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["ai_pr_review"] = ai_pr_review
SPEC.loader.exec_module(ai_pr_review)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def make_config(tmpdir, **overrides):
    repository = overrides.pop("repository", "owner/repo")
    event = {
        "pull_request": {
            "number": 7,
            "head": {
                "sha": "abc123",
                "repo": {"full_name": repository},
            },
            "base": {"repo": {"full_name": repository}},
        }
    }
    event_path = Path(tmpdir) / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    values = {
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_REPOSITORY": repository,
        "GITHUB_TOKEN": "github-token",
        "OPENCODE_GO_API_KEY": "opencode-secret",
    }
    values.update(overrides)
    return ai_pr_review.load_config(values)


class ConfigurationTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                tmpdir,
                OPENCODE_GO_MODEL="custom-model",
                OPENCODE_GO_ENDPOINT="https://opencode.ai/zen/go/v1/responses",
                OPENCODE_GO_PROTOCOL="responses",
            )
        self.assertEqual(config.model, "custom-model")
        self.assertEqual(config.protocol, "responses")
        self.assertEqual(config.pull_request, 7)

    def test_invalid_endpoint_protocol_pair_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ai_pr_review.ReviewError):
                make_config(
                    tmpdir,
                    OPENCODE_GO_ENDPOINT="https://opencode.ai/zen/go/v1/responses",
                )

    def test_missing_secret_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ai_pr_review.ReviewError):
                make_config(tmpdir, OPENCODE_GO_API_KEY="")

    def test_fork_is_not_same_repository(self):
        event = {
            "pull_request": {
                "head": {"repo": {"full_name": "contributor/repo"}},
                "base": {"repo": {"full_name": "owner/repo"}},
            }
        }
        self.assertFalse(ai_pr_review.is_same_repository_pull_request(event, "owner/repo"))


class DiffAndRedactionTests(unittest.TestCase):
    def test_excludes_binary_and_generated_files(self):
        diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new\n"
            "diff --git a/photo.png b/photo.png\n"
            "Binary files a/photo.png and b/photo.png differ\n"
            "diff --git a/clearest_frames/frame.png b/clearest_frames/frame.png\n"
            "Binary files a/clearest_frames/frame.png and b/clearest_frames/frame.png differ\n"
        )
        selection = ai_pr_review.select_diff(diff, 10_000, 100)
        self.assertIn("src/main.py", selection.text)
        self.assertNotIn("photo.png", selection.text)
        self.assertEqual(set(selection.skipped_paths), {"photo.png", "clearest_frames/frame.png"})
        self.assertEqual(selection.included_files, 1)

    def test_diff_is_bounded_and_reports_truncation(self):
        selection = ai_pr_review.select_diff("diff --git a/a.py b/a.py\n" + ("+line\n" * 100), 60, 4)
        self.assertTrue(selection.truncated)
        self.assertIn("diff truncated", selection.text)
        self.assertLessEqual(len(selection.text.encode("utf-8")), 60)

    def test_redacts_common_credentials(self):
        text = (
            "Authorization: Bearer bearer-secret-value\n"
            "api_key = 'plain-api-key-value'\n"
            "token=ghp_abcdefghijklmnopqrstuvwxyz\n"
            "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
        )
        redacted = ai_pr_review.redact_sensitive(text)
        self.assertNotIn("bearer-secret-value", redacted)
        self.assertNotIn("plain-api-key-value", redacted)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("BEGIN PRIVATE KEY", redacted)


class ProviderTests(unittest.TestCase):
    def test_chat_request_and_response_are_validated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
        opener = FakeOpener(
            [
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"summary":"Looks good","findings":[]}'
                            }
                        }
                    ]
                }
            ]
        )
        review = ai_pr_review.call_opencode(config, "review prompt", "session-7", opener)
        request, timeout = opener.requests[0]
        body = json.loads(request.data.decode("utf-8"))
        headers = dict(request.header_items())
        self.assertEqual(review.summary, "Looks good")
        self.assertEqual(body["model"], ai_pr_review.DEFAULT_MODEL)
        self.assertNotIn("opencode-secret", request.data.decode("utf-8"))
        self.assertEqual(headers["X-opencode-session"], "session-7")
        self.assertGreater(timeout, 0)

    def test_responses_protocol_is_supported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(
                tmpdir,
                OPENCODE_GO_ENDPOINT="https://opencode.ai/zen/go/v1/responses",
                OPENCODE_GO_PROTOCOL="responses",
            )
        opener = FakeOpener(
            [{"output_text": '{"summary":"Reviewed","findings":[]}'}]
        )
        review = ai_pr_review.call_opencode(config, "review prompt", "session-8", opener)
        self.assertEqual(review.summary, "Reviewed")
        body = json.loads(opener.requests[0][0].data.decode("utf-8"))
        self.assertIn("input", body)

    def test_malformed_response_and_provider_error_are_rejected(self):
        with self.assertRaises(ai_pr_review.ReviewError):
            ai_pr_review.parse_review("not json")
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
        opener = FakeOpener([ai_pr_review.URLError("provider detail")])
        with self.assertRaisesRegex(ai_pr_review.ReviewError, "HTTP request failed"):
            ai_pr_review.call_opencode(config, "prompt", "session", opener)


class CommentTests(unittest.TestCase):
    def test_comment_is_advisory_and_does_not_include_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
        selection = ai_pr_review.DiffSelection("secret prompt text", (), False, 1)
        review = ai_pr_review.Review(
            "Review summary",
            (
                {
                    "severity": "high",
                    "file": "src/main.py",
                    "line": 12,
                    "title": "Unsafe behavior",
                    "detail": "This needs attention.",
                },
            ),
        )
        body = ai_pr_review.render_comment(review, config, selection, "abc123")
        self.assertIn(ai_pr_review.MARKER, body)
        self.assertIn("advisory", body)
        self.assertIn("src/main.py", body)
        self.assertNotIn("secret prompt text", body)
        self.assertNotIn("opencode-secret", body)

    def test_existing_bot_comment_is_updated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
        opener = FakeOpener(
            [
                [{"id": 42, "body": ai_pr_review.MARKER, "user": {"login": "github-actions[bot]"}}],
                {},
            ]
        )
        ai_pr_review.publish_comment(config, "new body", opener)
        request, _ = opener.requests[1]
        self.assertEqual(request.method, "PATCH")
        self.assertTrue(request.full_url.endswith("/issues/comments/42"))

    def test_missing_bot_comment_is_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = make_config(tmpdir)
        opener = FakeOpener([[{"id": 1, "body": "human comment", "user": {"login": "person"}}], {}])
        ai_pr_review.publish_comment(config, "new body", opener)
        request, _ = opener.requests[1]
        self.assertEqual(request.method, "POST")
        self.assertTrue(request.full_url.endswith("/issues/7/comments"))


class WorkflowTests(unittest.TestCase):
    def test_workflow_is_base_controlled_and_does_not_checkout_pr_head(self):
        workflow = (SCRIPT_PATH.parents[1] / "workflows" / "opencode-go-pr-review.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("types: [opened]", workflow)
        self.assertIn("head.repo.full_name == github.repository", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertNotIn("head.sha }}", workflow.split("ref:", 1)[-1].splitlines()[0])
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("OPENCODE_GO_API_KEY", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("issues: write", workflow)
        self.assertNotIn("actions/checkout@v", workflow)


if __name__ == "__main__":
    unittest.main()
