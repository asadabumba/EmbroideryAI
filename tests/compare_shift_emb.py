from pathlib import Path
import olefile
import hashlib


ORIGINAL = Path(r"C:\Users\SA88\EmbroideryAI\dataset\raw\2 мишки-страз.EMB")
SHIFTED = Path(r"C:\Users\SA88\EmbroideryAI\dataset\raw\2 мишки-страз_x.EMB")


def get_streams(path):
    ole = olefile.OleFileIO(path)

    result = {}

    for stream in ole.listdir():
        name = "/".join(stream)
        data = ole.openstream(stream).read()

        result[name] = data

    ole.close()
    return result


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compare_bytes(a, b):
    length = min(len(a), len(b))

    changed = []

    for i in range(length):
        if a[i] != b[i]:
            changed.append(i)

    return changed


def main():

    import os

    print("CURRENT DIR:", os.getcwd())
    print("ORIGINAL EXISTS:", ORIGINAL.exists())
    print("SHIFTED EXISTS:", SHIFTED.exists())

    print("=" * 80)
    print("COMPARE ORIGINAL EMB VS SHIFTED EMB")
    print("=" * 80)

    orig = get_streams(ORIGINAL)
    shift = get_streams(SHIFTED)


    print("\nSTREAMS:")
    for name in orig:
        print(
            name,
            "size:",
            len(orig[name]),
            "hash:",
            sha(orig[name])[:12]
        )


    print("\nCHANGED STREAMS")
    print("=" * 80)


    for name in orig:

        if name not in shift:
            continue

        if orig[name] == shift[name]:
            continue


        diff = compare_bytes(
            orig[name],
            shift[name]
        )

        print()
        print("STREAM:", name)
        print("OLD SIZE:", len(orig[name]))
        print("NEW SIZE:", len(shift[name]))
        print("CHANGED BYTES:", len(diff))


        if diff:
            print(
                "RANGE:",
                min(diff),
                "-",
                max(diff)
            )

            print("FIRST CHANGES:")

            for pos in diff[:20]:
                print(
                    pos,
                    hex(orig[name][pos]),
                    "->",
                    hex(shift[name][pos])
                )


if __name__ == "__main__":
    main()