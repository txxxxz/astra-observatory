#!/usr/bin/env python3
"""Load the authentic exam generator, verifying the supplied image tar hash.

Use --image-tar for an existing question-package tar, --archive for its zip,
or no arguments to download the publicly supplied question package.
"""

import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile

EXPECTED_SHA256 = "282dad9d5d847aac0b26de6aa8391da01aff9701b922e6510731a915833d87a5"
PACKAGE_URL = (
    "https://raw.githubusercontent.com/TD-ding/space/main/"
    + urllib.parse.quote("宇宙万物观测站候选人发题包.zip")
)
IMAGE = "talkingdata/flightgen:exam-v4-f1"


def copy_bounded(source, target, maximum):
    size = 0
    while chunk := source.read(1024 * 1024):
        size += len(chunk)
        if size > maximum:
            raise ValueError("Package exceeds expected size bound")
        target.write(chunk)
    return size


def load_image(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    actual = checksum.hexdigest()
    if actual != EXPECTED_SHA256:
        raise ValueError(
            f"Image tar SHA256 mismatch: expected {EXPECTED_SHA256}, got {actual}"
        )
    loaded = subprocess.run(
        ["docker", "load", "-i", str(path)], check=True, capture_output=True, text=True
    )
    metadata = json.loads(
        subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True)
    )[0]
    if metadata["Architecture"] != "arm64" or metadata["Os"] != "linux":
        raise ValueError("Expected the supplied linux/arm64 generator image")
    print(
        json.dumps(
            {
                "image": IMAGE,
                "sha256": actual,
                "image_id": metadata["Id"],
                "architecture": metadata["Architecture"],
                "os": metadata["Os"],
                "load_output": loaded.stdout.strip(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image-tar", type=pathlib.Path)
    source.add_argument("--archive", type=pathlib.Path)
    args = parser.parse_args()
    if args.image_tar:
        load_image(args.image_tar.resolve())
        return
    with tempfile.TemporaryDirectory(prefix="observatory-generator-") as directory:
        temporary = pathlib.Path(directory)
        archive = args.archive
        if archive is None:
            archive = temporary / "candidate-package.zip"
            with (
                urllib.request.urlopen(PACKAGE_URL, timeout=60) as response,
                archive.open("wb") as output,
            ):
                copy_bounded(response, output, 64 * 1024**2)
        with zipfile.ZipFile(archive) as package:
            matches = [
                item
                for item in package.infolist()
                if pathlib.PurePosixPath(item.filename).name == "flightgen-image.tar"
                and not item.is_dir()
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Expected exactly one flightgen-image.tar in the question package"
                )
            image_tar = temporary / "flightgen-image.tar"
            with (
                package.open(matches[0]) as source_stream,
                image_tar.open("wb") as output,
            ):
                copy_bounded(source_stream, output, 128 * 1024**2)
        load_image(image_tar)


if __name__ == "__main__":
    main()
