import os
import sys
import zlib
import json
import mmap
import struct
from pathlib import Path

CHUNK_SIZE = 1024 * 1024
MAGIC = b"HDOG\x00"
UNITY_MAGIC = b"UnityFS\x00"

def extract_hdog(source):
    source = Path(source)
    output = source.parent / (source.stem + "_extracted")
    output.mkdir(exist_ok=True)

    print(f"\nProcessing: {source.name}")
    print(f"File size: {source.stat().st_size:,} bytes")

    with source.open("rb") as f:
        header = f.read(5)

        if header != MAGIC:
            print("Invalid HDOG header!")
            return

        decoder = zlib.decompressobj(31)
        metadata_path = output / "metadata.json"
        payload_path = output / "payload.bin"

        with metadata_path.open("wb") as meta:
            with payload_path.open("wb") as payload:
                while True:
                    chunk = f.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    decompressed = decoder.decompress(chunk)
                    meta.write(decompressed)

                    if decoder.eof:
                        payload.write(decoder.unused_data)

                        while True:
                            remaining = f.read(CHUNK_SIZE)
                            if not remaining:
                                break
                            payload.write(remaining)

                        break

                if not decoder.eof:
                    raise ValueError(
                        "GZIP stream did not finish correctly."
                    )

    print(f"Metadata extracted: {metadata_path}")
    print(f"Raw payload extracted: {payload_path}")

    try:
        with metadata_path.open("r", encoding="utf-8") as f:
            metadata = json.load(f)

        print("JSON metadata successfully parsed.")

        with (output / "metadata_pretty.json").open(
            "w", encoding="utf-8"
        ) as f:
            json.dump(metadata, f, indent=4)

    except Exception as e:
        print(f"JSON parsing warning: {e}")

    bundles_dir = output / "bundles"
    bundles_dir.mkdir(exist_ok=True)

    bundle_count = 0
    payload_size = payload_path.stat().st_size

    if payload_size:
        with payload_path.open("rb") as f:
            with mmap.mmap(
                f.fileno(), 0, access=mmap.ACCESS_READ
            ) as data:

                position = 0

                while True:
                    start = data.find(UNITY_MAGIC, position)

                    if start == -1:
                        break

                    try:
                        cursor = start + len(UNITY_MAGIC)

                        # UnityFS format version
                        version = struct.unpack(
                            ">I", data[cursor:cursor + 4]
                        )[0]
                        cursor += 4

                        # Read null-terminated strings
                        def read_string(pos):
                            end = data.find(b"\x00", pos)
                            if end == -1:
                                raise ValueError("Invalid string")
                            value = data[pos:end].decode(
                                "utf-8", errors="replace"
                            )
                            return value, end + 1

                        player_version, cursor = read_string(cursor)
                        engine_version, cursor = read_string(cursor)

                        # Total bundle size
                        total_size = struct.unpack(
                            ">Q", data[cursor:cursor + 8]
                        )[0]

                        if total_size <= cursor - start:
                            raise ValueError("Invalid bundle size")

                        end = start + total_size

                        if end > len(data):
                            raise ValueError("Bundle exceeds payload")

                        bundle_count += 1

                        bundle_path = (
                            bundles_dir /
                            f"bundle_{bundle_count:03d}.unity3d"
                        )

                        with bundle_path.open("wb") as out:
                            out.write(data[start:end])

                        print(f"\nFound UnityFS bundle #{bundle_count}")
                        print(f"  Offset: {start:#x}")
                        print(f"  Size: {total_size:,} bytes")
                        print(f"  Format: {version}")
                        print(f"  Player: {player_version}")
                        print(f"  Engine: {engine_version}")
                        print(f"  Saved: {bundle_path.name}")

                        position = end

                    except Exception as e:
                        print(
                            f"Possible UnityFS at {start:#x}, "
                            f"but couldn't parse it: {e}"
                        )
                        position = start + 1

    print(f"\nFinished: {source.name}")
    print(f"UnityFS bundles found: {bundle_count}")
    print(f"Output directory: {output}")


def main():
    if len(sys.argv) > 1:
        files = [Path(p) for p in sys.argv[1:]]
    else:
        files = list(Path(".").glob("*.hdog"))

    if not files:
        print("There are no Hdog files in this directory.")
        return

    for file in files:
        try:
            extract_hdog(file)
        except Exception as e:
            print(f"ERROR processing {file.name}: {e}")


if __name__ == "__main__":
    main()
