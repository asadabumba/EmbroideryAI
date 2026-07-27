from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


dst = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
    / "rose.dst"
)


data = dst.read_bytes()


HEADER = 512


commands = data[HEADER:]


print("Всего командных байт:", len(commands))


print("\nFIRST COMMANDS")


for i in range(0, 60, 3):

    cmd = commands[i:i+3]

    print(
        HEADER+i,
        cmd.hex(" ")
    )