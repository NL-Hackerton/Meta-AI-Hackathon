import json
import re
import subprocess
from pathlib import Path


def test_sample_is_ten_second_hd_video(tmp_path):
    output = tmp_path / "sample.mp4"
    subprocess.run(["bash", "tests/fixtures/make_sample.sh", str(output)], check=True)
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]
        )
    )
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1920, 1080)
    assert video["codec_name"] == "h264"
    assert float(probe["format"]["duration"]) == 10.0
    frames = (
        subprocess.check_output(
            ["ffmpeg", "-v", "error", "-i", str(output), "-map", "0:v", "-f", "framemd5", "-"]
        )
        .decode()
        .splitlines()
    )
    hashes = [line.rsplit(",", 1)[-1].strip() for line in frames if not line.startswith("#")]
    assert hashes[0] != hashes[-1]


def test_no_credentials_in_tracked_text():
    patterns = [
        rb"gh[pousr]_" + rb"[A-Za-z0-9]{30,}",
        rb"EAAB" + rb"[A-Za-z0-9]{40,}",
        rb"-----BEGIN " + rb"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    ]
    paths = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    offenders = []
    for raw in paths:
        if not raw:
            continue
        path = Path(raw.decode())
        if not path.is_file():
            continue
        content = path.read_bytes()
        if b"\0" in content[:8192]:
            continue
        if any(re.search(pattern, content) for pattern in patterns):
            offenders.append(str(path))
    assert not offenders, f"Credential-like content in: {offenders}"
