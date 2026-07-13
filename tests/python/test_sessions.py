from codex_bridge.sessions import normalize_session_list


ACTIVE_ID = "019c0000-0000-7000-8000-000000000001"
RECENT_ID = "019c0000-0000-7000-8000-000000000002"
IDLE_ID = "019c0000-0000-7000-8000-000000000003"


def test_normalize_session_list_classifies_only_reported_active_threads():
    response = {
        "data": [
            {
                "id": RECENT_ID,
                "name": None,
                "preview": "Resume the dashboard work\nwith private detail",
                "cwd": "/home/user/Code/Widgets",
                "source": "vscode",
                "status": {"type": "notLoaded"},
                "createdAt": 100,
                "updatedAt": 220,
                "turns": [{"private": "discard me"}],
            },
            {
                "id": ACTIVE_ID,
                "name": "Live monitor session",
                "preview": "unused preview",
                "cwd": "/home/user/Code/Widgets",
                "source": "cli",
                "status": {
                    "type": "active",
                    "activeFlags": ["waitingOnApproval", "unknownFlag"],
                },
                "createdAt": 110,
                "updatedAt": 210,
                "extra": {"secret": "discard me"},
            },
            {
                "id": IDLE_ID,
                "preview": "Idle work",
                "cwd": "/home/user/Code/Other",
                "source": {"custom": "desktop"},
                "status": {"type": "idle"},
                "createdAt": 120,
                "updatedAt": 230,
            },
        ]
    }

    result = normalize_session_list(response, limit=12)

    assert [row["id"] for row in result["active"]] == [ACTIVE_ID]
    assert [row["id"] for row in result["recent"]] == [IDLE_ID, RECENT_ID]
    assert result["active"][0]["attention"] == ["waitingOnApproval"]
    assert result["recent"][1]["statusLabel"] == "Ready to resume"
    assert result["recent"][1]["title"] == "Resume the dashboard work"
    assert result["recent"][1]["sourceLabel"] == "VS Code"
    assert "private" not in repr(result)
    assert "secret" not in repr(result)


def test_normalize_session_list_rejects_invalid_rows_and_bounds_text():
    response = {
        "data": [
            {"id": "not-a-uuid", "preview": "invalid"},
            {
                "id": ACTIVE_ID,
                "preview": " x " * 200,
                "cwd": "relative/path",
                "source": {"subAgent": "review"},
                "status": {"type": "systemError"},
                "createdAt": "bad",
                "updatedAt": 20,
            },
        ]
    }

    result = normalize_session_list(response, limit=1)

    assert len(result["recent"]) == 1
    assert len(result["recent"][0]["title"]) <= 160
    assert result["recent"][0]["cwd"] is None
    assert result["recent"][0]["sourceLabel"] == "Sub-agent"
    assert result["recent"][0]["createdAt"] is None


def test_normalize_session_list_handles_invalid_top_level_response():
    assert normalize_session_list(None) == {"active": [], "recent": []}
    assert normalize_session_list({"data": "invalid"}) == {
        "active": [],
        "recent": [],
    }


def test_normalize_session_list_never_stringifies_non_text_preview_data():
    result = normalize_session_list(
        {
            "data": [
                {
                    "id": IDLE_ID,
                    "preview": {"secret": "must not render"},
                    "status": {"type": "idle"},
                    "updatedAt": 10,
                }
            ]
        }
    )

    assert result["recent"][0]["title"] == "Untitled session"
    assert "must not render" not in repr(result)
