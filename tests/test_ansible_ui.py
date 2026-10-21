import pytest
from pydantic import ValidationError

from ansible_ui import PLAYBOOK_PATH, RunRequest, build_ansible_command


def test_build_ansible_command_runs_selected_tags():
    command = build_ansible_command("/usr/bin/ansible-playbook", ["quality", "tests"])

    assert command == [
        "/usr/bin/ansible-playbook",
        str(PLAYBOOK_PATH),
        "--tags",
        "quality,tests",
    ]


def test_build_ansible_command_without_tags_runs_all_steps():
    assert build_ansible_command("/usr/bin/ansible-playbook", None) == [
        "/usr/bin/ansible-playbook",
        str(PLAYBOOK_PATH),
    ]


def test_run_request_rejects_unlisted_tags():
    with pytest.raises(ValidationError):
        RunRequest(tags=["quality", "--extra-vars"])
