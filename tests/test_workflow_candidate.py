import http.server
import os
import shutil
import subprocess
import threading

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows", "schedule.yml")


@pytest.fixture(scope="module")
def wf():
    with open(WF, encoding="utf-8") as f:
        return yaml.safe_load(f)


def steps(wf):
    return wf["jobs"]["run-bot"]["steps"]


def test_pause_condition_and_triggers_unchanged(wf):
    assert wf["jobs"]["run-bot"]["if"] == "${{ false }}"
    on = wf.get("on", wf.get(True))
    assert on["schedule"] == [{"cron": "30 21 * * 1-5"}]
    assert "workflow_dispatch" in on and set(on) == {"schedule", "workflow_dispatch"}


def test_existing_steps_kept_and_run_step_has_id(wf):
    st = steps(wf)
    assert [s.get("name") for s in st][:4] == [
        "Checkout repository", "Setup Python", "Install dependencies", "Run script"]
    run = st[3]
    assert run["id"] == "run" and run["run"] == "python main.py"
    assert run["env"]["SHEETS_ENABLED"] == "true"
    assert set(run["env"]) == {"DISCORD_WEBHOOK_URL", "SPREADSHEET_ID", "GCP_CREDENTIALS",
                               "SHEETS_ENABLED", "TARGET_SESSION_DATE"}


def test_reporter_runs_only_when_app_was_skipped_after_failure(wf):
    rep = steps(wf)[-1]
    assert rep["name"] == "Report setup failure"
    assert rep["if"] == "${{ failure() && steps.run.outcome == 'skipped' }}"
    assert set(rep["env"]) == {"DISCORD_WEBHOOK_URL"}
    assert "continue-on-error" not in rep  # 報告成否で先行の失敗を成功へ変えない
    assert "pip" not in rep["run"] and "python" not in rep["run"]  # 追加依存なし


def _run_reporter(wf, url):
    script = steps(wf)[-1]["run"]
    env = {"PATH": os.environ["PATH"], "DISCORD_WEBHOOK_URL": url}
    return subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True,
                          text=True, timeout=60)


@pytest.fixture
def server():
    received = []

    class H(http.server.BaseHTTPRequestHandler):
        status = 204

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            received.append((self.path, self.rfile.read(n).decode()))
            self.send_response(type(self).status)
            self.end_headers()

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd, H, received
    httpd.shutdown()


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="bash/curl が必要")
class TestReporterScript:
    def test_success_sends_once_and_hides_url(self, wf, server):
        httpd, H, received = server
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/webhooks/SECRET_WEBHOOK_TOKEN_123"
        r = _run_reporter(wf, url)
        assert r.returncode == 0 and len(received) == 1
        assert "実行準備" in received[0][1] and "条件未達ではありません" in received[0][1]
        assert "SECRET_WEBHOOK_TOKEN_123" not in r.stdout + r.stderr
        assert "HTTP 204" in r.stdout

    def test_http_failure_is_nonzero(self, wf, server):
        httpd, H, received = server
        H.status = 500
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/webhooks/SECRET_WEBHOOK_TOKEN_123"
        r = _run_reporter(wf, url)
        assert r.returncode != 0 and len(received) == 1  # 再送なし
        assert "SECRET_WEBHOOK_TOKEN_123" not in r.stdout + r.stderr

    def test_unreachable_is_nonzero_and_hides_url(self, wf):
        r = _run_reporter(wf, "http://127.0.0.1:9/api/webhooks/SECRET_WEBHOOK_TOKEN_123")
        assert r.returncode != 0
        assert "SECRET_WEBHOOK_TOKEN_123" not in r.stdout + r.stderr

    def test_missing_webhook_is_nonzero(self, wf):
        assert _run_reporter(wf, "").returncode != 0
