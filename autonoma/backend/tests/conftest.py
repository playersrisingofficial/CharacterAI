import os
import tempfile

import pytest

# Isolate each test session in a throwaway data dir before app import.
_tmp = tempfile.mkdtemp(prefix="autonoma-test-")
os.environ["AUTONOMA_DATA_DIR"] = _tmp
os.environ["AUTONOMA_AUTOMATION_BACKEND"] = "simulated"
os.environ.setdefault("AUTONOMA_SIM_STEP_SECONDS", "0.05")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_skill():
    return {
        "name": "LoginToApp",
        "description": "Logs into a desktop application.",
        "skill_type": "form_filling",
        "status": "active",
        "input_schema": {
            "type": "object",
            "properties": {"username": {"type": "string"},
                           "password_secret_ref": {"type": "string"}},
            "required": ["username", "password_secret_ref"],
        },
        "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}},
                          "required": ["success"]},
        "execution_plan": [
            {"step": 1, "action": "focus_window", "target": "AppLogin", "mode": "human_like"},
            {"step": 2, "action": "type", "field": "username",
             "value": "{{input.username}}", "mode": "human_like",
             "expect": {"field_value": "{{input.username}}"}},
        ],
        "constraints": {"allowed_windows": ["AppLogin"],
                        "forbidden_actions": ["file_delete"]},
        "behavior_profile": {"default_mode": "human_like",
                             "human_like": {"mouse_speed_range": [0.4, 1.2],
                                            "typing_wpm_range": [45, 90],
                                            "micro_delay_ms_range": [50, 300]},
                             "machine_speed": {"allow_clipboard_paste": True,
                                               "artificial_delay_ms": 0}},
    }
