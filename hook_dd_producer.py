import frida
import psutil

pid = next(
    p.info["pid"]
    for p in psutil.process_iter(["pid", "name"])
    if (p.info["name"] or "").lower() == "es.exe"
)

session = frida.attach(pid)

js = r'''
function mod(name) {
    name = name.toLowerCase();

    for (const m of Process.enumerateModules()) {
        if (m.name.toLowerCase() === name)
            return m;
    }

    throw new Error("not found: " + name);
}

const imp = mod("Import.dll");

const before = imp.base.add(0x3D4C17);
const after  = imp.base.add(0x3D4C1A);

let pending = {};

send({
    event: "ready",
    before: before.toString(),
    after: after.toString()
});

Interceptor.attach(before, {
    onEnter(args) {
        const c = this.context;

        const target = c.r9;
        const buffer = c.rdi;
        const object = c.rsi;
        const size = c.rbx.toUInt32();

        let vt = ptr(0);

        try {
            vt = object.readPointer();
        } catch (e) {}

        pending[this.threadId] = {
            target: target,
            buffer: buffer,
            size: size,
            object: object
        };

        send({
            event: "before",
            thread: this.threadId,
            target: target.toString(),
            target_symbol:
                DebugSymbol.fromAddress(target).toString(),
            object: object.toString(),
            vtable: vt.toString(),
            buffer: buffer.toString(),
            size: size
        });
    }
});

Interceptor.attach(after, {
    onEnter(args) {
        const p = pending[this.threadId];

        if (!p)
            return;

        let head = "";

        try {
            const n = Math.min(p.size, 64);
            const bytes = p.buffer.readByteArray(n);

            head = Array.from(
                new Uint8Array(bytes)
            ).map(
                x => x.toString(16).padStart(2, "0")
            ).join(" ");
        } catch (e) {
            head = "<READ FAILED: " + e + ">";
        }

        send({
            event: "after",
            thread: this.threadId,
            target: p.target.toString(),
            buffer: p.buffer.toString(),
            size: p.size,
            head: head
        });

        delete pending[this.threadId];
    }
});
'''

script = session.create_script(js)

def on_message(message, data):
    if message["type"] == "error":
        print(message.get("stack", message))
        return

    p = message.get("payload", {})
    event = p.get("event")

    if event == "ready":
        print("HOOK READY")
        print("before:", p["before"])
        print("after: ", p["after"])
        print()
        print("Сделай изменение и Ctrl+S. Жди вывода.")
        print()

    elif event == "before":
        print("\n=== PRODUCER CALL ===")
        print("TARGET :", p["target"])
        print("SYMBOL :", p["target_symbol"])
        print("OBJECT :", p["object"])
        print("VTABLE :", p["vtable"])
        print("BUFFER :", p["buffer"])
        print("SIZE   :", p["size"])

    elif event == "after":
        print("\n=== PRODUCER RETURN ===")
        print("TARGET :", p["target"])
        print("BUFFER :", p["buffer"])
        print("SIZE   :", p["size"])
        print("HEAD   :", p["head"])
        print("=======================\n")

script.on("message", on_message)
script.load()

import time
time.sleep(60)

script.unload()
session.detach()
