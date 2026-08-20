import frida
import psutil
import json
from pathlib import Path

OUT = Path("logs/frida_serialization")
OUT.mkdir(parents=True, exist_ok=True)

BIN = OUT / "serialize_writes.bin"
LOG = OUT / "serialize_writes.jsonl"

BIN.write_bytes(b"")
LOG.write_text("", encoding="utf-8")

pid = next(
    p.info["pid"]
    for p in psutil.process_iter(["pid", "name"])
    if (p.info["name"] or "").lower() == "es.exe"
)

session = frida.attach(pid)

js = r'''
function moduleByName(name) {
    const wanted = name.toLowerCase();

    for (const m of Process.enumerateModules()) {
        if (m.name.toLowerCase() === wanted)
            return m;
    }

    throw new Error("Module not found: " + name);
}

const imp = moduleByName("Import.dll");
const wes = moduleByName("Wessys.dll");

const serialize = imp.base.add(0x4FDF60);
const writeFunc = wes.base.add(0x48550);

console.log("ArchiveEmbedded::Serialize @ " + serialize);
console.log("ESDArchiveStream::Write    @ " + writeFunc);

const active = {};
let sessionId = 0;
let writeId = 0;

Interceptor.attach(serialize, {
    onEnter(args) {
        const tid = this.threadId;

        if (!active[tid]) {
            sessionId++;

            active[tid] = {
                depth: 0,
                session: sessionId
            };

            send({
                event: "serialize_begin",
                session: sessionId,
                thread: tid,
                archive: args[0].toString(),
                document: args[1].toString(),
                arg3: args[2].toUInt32()
            });
        }

        active[tid].depth++;
    },

    onLeave(retval) {
        const tid = this.threadId;
        const state = active[tid];

        if (!state)
            return;

        state.depth--;

        if (state.depth === 0) {
            send({
                event: "serialize_end",
                session: state.session,
                thread: tid
            });

            delete active[tid];
        }
    }
});

Interceptor.attach(writeFunc, {
    onEnter(args) {
        const tid = this.threadId;
        const state = active[tid];

        if (!state)
            return;

        const buf = args[1];
        const size = args[2].toUInt32();

        if (size === 0 || buf.isNull())
            return;

        writeId++;

        let bytes = null;

        try {
            bytes = buf.readByteArray(size);
        } catch (e) {
            send({
                event: "read_error",
                session: state.session,
                write: writeId,
                thread: tid,
                address: buf.toString(),
                size: size,
                error: e.toString()
            });

            return;
        }

        send({
            event: "write",
            session: state.session,
            write: writeId,
            thread: tid,
            address: buf.toString(),
            size: size
        }, bytes);
    }
});

send({
    event: "ready",
    pid: Process.id
});
'''

script = session.create_script(js)

total = 0
writes = 0

def on_message(message, data):
    global total, writes

    if message["type"] == "error":
        print("\nFRIDA ERROR:")
        print(message.get("stack", message))
        return

    payload = message.get("payload", {})
    event = payload.get("event")

    if event == "ready":
        print("\nHOOK READY")
        print("PID:", payload["pid"])
        print("Сделай ОДИН Ctrl+S в Wilcom.")
        print("После сохранения вернись сюда и нажми Enter.\n")
        return

    if event == "serialize_begin":
        print(
            f"[SERIALIZE BEGIN] "
            f"session={payload['session']} "
            f"thread={payload['thread']} "
            f"arg3=0x{payload['arg3']:X}"
        )

    elif event == "write":
        offset = total
        size = payload["size"]

        with BIN.open("ab") as f:
            f.write(data or b"")

        record = dict(payload)
        record["output_offset"] = offset

        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        writes += 1
        total += len(data or b"")

        print(
            f"[WRITE {writes:4d}] "
            f"size={size:7d} "
            f"total={total:8d}"
        )

    elif event == "serialize_end":
        print(
            f"[SERIALIZE END] "
            f"session={payload['session']}"
        )

    elif event == "read_error":
        print("[READ ERROR]", payload)

script.on("message", on_message)
script.load()

input()

print("\n=== RESULT ===")
print("WRITE CALLS:", writes)
print("CAPTURED:   ", total, "bytes")
print("BIN:        ", BIN.resolve())
print("LOG:        ", LOG.resolve())

script.unload()
session.detach()
