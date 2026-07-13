import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
UUID = "codex-monitor@breixopd"


def test_installer_keeps_one_copy_and_removes_all_install_backups(tmp_path):
    data_home = tmp_path / "share"
    applets = data_home / "cinnamon" / "applets"
    target = applets / UUID
    target.mkdir(parents=True)
    (target / "old-marker").write_text("old", encoding="utf-8")
    for suffix in ("20260713-100000", "20260713-110000"):
        stale = applets / f"{UUID}.backup-{suffix}"
        stale.mkdir()
        (stale / "metadata.json").write_text("{}", encoding="utf-8")
    unrelated = applets / "unrelated@example"
    unrelated.mkdir()
    backup_root = data_home / UUID / "install-backups"
    retained = backup_root / "old-retained-copy"
    retained.mkdir(parents=True)
    (retained / "old-marker").write_text("old", encoding="utf-8")

    completed = subprocess.run(
        ["sh", str(ROOT / "scripts" / "install.sh")],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "XDG_DATA_HOME": str(data_home)},
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    matching = sorted(path.name for path in applets.iterdir() if path.name.startswith(UUID))
    assert matching == [UUID]
    assert (target / "metadata.json").is_file()
    assert unrelated.is_dir()
    assert not backup_root.exists()
    assert not any(path.name.startswith(".codex-monitor.previous.") for path in applets.iterdir())
