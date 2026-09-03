"""Build the private runner from pinned Uncover sources; all tooling stays local."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = "3f7b74af20b24a7d5477d1dc77f6ba881219b0de"
GO_VERSION = "go1.27.1"
GO_SHA256 = "a3911b5e0e1b1053f25ed0675f4c1c6aad1e2bfcf253df2b9be4caabd2edd95d"


def main():
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    go = runtime / "go/bin/go.exe"
    if not go.exists():
        archive = runtime / f"{GO_VERSION}.windows-amd64.zip"
        if not archive.exists():
            urllib.request.urlretrieve(f"https://go.dev/dl/{archive.name}", archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != GO_SHA256:
            raise RuntimeError("Go archive checksum mismatch")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(runtime)
    source = runtime / "uncover-src"
    if not source.exists():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", "v1.2.1",
                        "https://github.com/projectdiscovery/uncover.git", str(source)], check=True)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise RuntimeError("Uncover source revision mismatch")
    # Never compile unreviewed changes to the pinned upstream source.
    subprocess.run(["git", "-C", str(source), "diff", "--exit-code", "HEAD", "--"], check=True)
    build_source = runtime / "uncover-build"
    shutil.copytree(source, build_source, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", ".github"))
    # The v1.2.1 parser dereferences WebpropertyV1 on host/certificate hits.
    # Keep the pinned checkout intact and apply this small compatibility fix only to the build copy.
    censys_file = build_source / "sources/agent/censys/censys.go"
    censys_text = censys_file.read_text(encoding="utf-8")
    marker = "for _, censysResult := range result.Hits {"
    if censys_text.count(marker) != 1:
        raise RuntimeError("Pinned Censys parser no longer matches")
    censys_text = censys_text.replace(marker, marker + '''
            if censysResult.HostV1 != nil {
                host := censysResult.HostV1.Resource
                if host.IP != nil {
                    if !sources.SendResult(ctx, results, sources.Result{Source: agent.Name(), IP: *host.IP}) {
                        return resp
                    }
                }
                continue
            }
            if censysResult.WebpropertyV1 == nil {
                continue
            }
''').replace("PerPage: MaxPerPage,", "PerPage: min(MaxPerPage, query.Limit),")
    censys_file.write_text(censys_text, encoding="utf-8")
    package = build_source / "cmd/spider-private"
    package.mkdir(parents=True, exist_ok=True)
    for path in (ROOT / "tools/uncover_bridge").glob("*.go"):
        shutil.copyfile(path, package / path.name)
    env = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in
           ("API_KEY", "API_TOKEN", "FOFA_", "CENSYS_", "SHODAN_"))}
    env.update(GOCACHE=str(runtime / "go-cache"), GOPATH=str(runtime / "go-work"),
               GOMODCACHE=str(runtime / "go-mod"), GOTOOLCHAIN="local", CGO_ENABLED="0")
    subprocess.run([str(go), "test", "./cmd/spider-private"], cwd=build_source, env=env, check=True)
    output = runtime / "uncover"
    output.mkdir(exist_ok=True)
    binary = output / "uncover-private.exe"
    subprocess.run([str(go), "build", "-trimpath", "-ldflags=-s -w", "-o", str(binary),
                    "./cmd/spider-private"], cwd=build_source, env=env, check=True)
    (output / "build.json").write_text(json.dumps({
        "upstream": "uncover v1.2.1", "revision": revision, "go": GO_VERSION,
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "bridge_sha256": hashlib.sha256((ROOT / "tools/uncover_bridge/main.go").read_bytes()).hexdigest(),
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    }, indent=2), encoding="utf-8")
    print("Private Uncover v1.2.1 runner built and tested.")


if __name__ == "__main__":
    main()
