from app.services.version_parser import parse_version, compare_versions, CompareResult, VersionKind

def run():
    samples = [
        "0.01 Fixed",
        "0.1.1a - Patreon",
        "Season 2 - Redux Demo",
        "build 38.2",
        "Version: v0.6",
        "Ver 1.0",
    ]
    for s in samples:
        vi = parse_version(s)
        assert vi is not None

    a = parse_version("0.1.0")
    b = parse_version("0.1.1")
    assert compare_versions(a, b) == CompareResult.OLDER
    assert compare_versions(b, a) == CompareResult.NEWER

    a = parse_version("0.1.1a")
    b = parse_version("0.1.1b")
    assert compare_versions(a, b) == CompareResult.OLDER

    a = parse_version("Season 2")
    b = parse_version("Season 2")
    assert compare_versions(a, b) == CompareResult.SAME

    a = parse_version("demo")
    b = parse_version("patreon")
    assert compare_versions(a, b) == CompareResult.UNKNOWN

if __name__ == "__main__":
    run()
    print("ok")
