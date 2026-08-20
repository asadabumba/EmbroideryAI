import frida
import psutil
import json
import math
import time
from pathlib import Path
from collections import Counter

OUT = Path("logs/frida_designdoc")
OUT.mkdir(parents=True, exist_ok=True)

BIN = OUT / "DesignDocument_writes.bin"
LOG = OUT / "DesignDocument_writes.jsonl"

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

// Confirmed SavePropertyInformation RVA
const saveProps = imp.base.add(0x597D50);

const ddStreams = {};
const hookedWriteFunctions = {};
let streamId = 0;
let writeId = 0;

function hookIStream(stream) {
    const key = stream.toString();

    if (ddStreams[key])
        return;

    streamId++;

    ddStreams[key] = {
        id: streamId
    };

    let vt;

    try {
        vt = stream.readPointer();
    } catch (e) {
        send({
            event: "error",
            where: "read vtable",
            error: e.toString()
        });
        return;
    }

    // IUnknown:
    // 0 QueryInterface
    // 1 AddRef
    // 2 Release
    //
    // ISequentialStream:
    // 3 Read
    // 4 Write
    const writeFunc = vt.add(
        4 * Process.pointerSize
    ).readPointer();

    send({
        event: "dd_stream",
        id: streamId,
        stream: key,
        vtable: vt.toString(),
        write: writeFunc.toString()
    });

    const writeKey = writeFunc.toString();

    if (hookedWriteFunctions[writeKey])
        return;

    hookedWriteFunctions[writeKey] = true;

    Interceptor.attach(writeFunc, {
        onEnter(args) {
            const thisPtr = args[0];
            const state = ddStreams[
                thisPtr.toString()
            ];

            if (!state)
                return;

            const buf = args[1];
            const size = args[2].toUInt32();

            if (
                buf.isNull()
                || size === 0
            )
                return;

            writeId++;

            let bytes;

            try {
                bytes = buf.readByteArray(size);
            } catch (e) {
                send({
                    event: "read_error",
                    stream_id: state.id,
                    write_id: writeId,
                    size: size,
                    error: e.toString()
                });

                return;
            }

            send({
                event: "write",
                stream_id: state.id,
                write_id: writeId,
                thread: this.threadId,
                buffer: buf.toString(),
                size: size
            }, bytes);
        }
    });
}

let createHooked = false;

function hookStorage(storage) {
    if (createHooked)
        return;

    let vt;

    try {
        vt = storage.readPointer();
    } catch (e) {
        return;
    }

    // IStorage:
    // 0 QI
    // 1 AddRef
    // 2 Release
    // 3 CreateStream
    const createStream = vt.add(
        3 * Process.pointerSize
    ).readPointer();

    createHooked = true;

    send({
        event: "create_hook",
        address: createStream.toString()
    });

    Interceptor.attach(createStream, {
        onEnter(args) {
            this.name = "";

            try {
                this.name = args[1].readUtf16String();
            } catch (e) {
                return;
            }

            // HRESULT CreateStream(
            //   name,
            //   mode,
            //   reserved1,
            //   reserved2,
            //   IStream **ppstm
            // )
            //
            // RCX=this, RDX=name, R8=mode, R9=reserved1,
            // reserved2 + ppstm are stack args.
            this.ppstm = args[5];

            send({
    event: "all_create",
    name: this.name,
    mode: args[2].toUInt32()
});

if (this.name === "DesignDocument") {
    send({
        event: "dd_create_enter",
        ppstm: this.ppstm.toString()
    });
}
        },

        onLeave(retval) {
            if (this.name !== "DesignDocument")
                return;

            const hr = retval.toInt32();

            send({
                event: "dd_create_leave",
                hresult: hr
            });

            if (hr !== 0)
                return;

            try {
                const stream = this.ppstm.readPointer();

                if (!stream.isNull())
                    hookIStream(stream);

            } catch (e) {
                send({
                    event: "error",
                    where: "read ppstm",
                    error: e.toString()
                });
            }
        }
    });
}

Interceptor.attach(saveProps, {
    onEnter(args) {
        send({
            event: "saveprops",
            storage: args[0].toString(),
            document: args[1].toString(),
            arg3: args[2].toUInt32()
        });

        hookStorage(args[0]);
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
        print("\nFRIDA ERROR")
        print(message.get("stack", message))
        return

    p = message.get("payload", {})
    event = p.get("event")

    if event == "ready":
        print("\nHOOK READY")
        print("PID:", p["pid"])
        print("Сделай изменение в EMB и ОДИН Ctrl+S.")
        print("Дождись полного сохранения, потом сюда -> Enter.\n")

    elif event == "saveprops":
        print(
            "[SAVE] "
            f"arg3=0x{p['arg3']:X}"
        )

    elif event == "create_hook":
        print(
            "[HOOK CreateStream]",
            p["address"]
        )

    elif event == "all_create":
        print(
            f"[CREATE] {p['name']!r} "
            f"mode=0x{p['mode']:X}"
        )

    elif event == "dd_create_enter":
        print(
            '[CreateStream] "DesignDocument"'
        )

    elif event == "dd_create_leave":
        print(
            "[DesignDocument CREATED] "
            f"HRESULT={p['hresult']}"
        )

    elif event == "dd_stream":
        print(
            "[DD IStream] "
            f"id={p['id']} "
            f"stream={p['stream']}"
        )

        print(
            "    Write =",
            p["write"]
        )

    elif event == "write":
        blob = data or b""

        offset = total

        with BIN.open("ab") as f:
            f.write(blob)

        rec = dict(p)
        rec["offset"] = offset

        with LOG.open(
            "a",
            encoding="utf-8"
        ) as f:
            f.write(
                json.dumps(rec)
                + "\n"
            )

        writes += 1
        total += len(blob)

        prefix = blob[:16].hex(" ")

        print(
            f"[DD WRITE {writes:3d}] "
            f"size={len(blob):7d} "
            f"total={total:7d} "
            f"head={prefix}"
        )

    elif event == "read_error":
        print(
            "[READ ERROR]",
            p
        )

    elif event == "error":
        print(
            "[HOOK ERROR]",
            p
        )

script.on("message", on_message)
script.load()

print("\nLISTENING 60 SECONDS — терминал не трогай.")
print("Сейчас измени дизайн в Wilcom и нажми Ctrl+S.\n")
time.sleep(60)

data = BIN.read_bytes()

print("\n=== RESULT ===")
print("WRITE CALLS:", writes)
print("CAPTURED:   ", len(data), "bytes")

if data:
    counts = Counter(data)
    n = len(data)

    entropy = -sum(
        (c / n) * math.log2(c / n)
        for c in counts.values()
    )

    print(
        "ENTROPY:    ",
        f"{entropy:.6f}",
        "bits/byte"
    )

    print(
        "FIRST 64:   ",
        data[:64].hex(" ")
    )

print("BIN:", BIN.resolve())
print("LOG:", LOG.resolve())

script.unload()
session.detach()


