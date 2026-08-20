import frida
import psutil
import time

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

const functionStart = imp.base.add(0x3D48C0);
const producerCall  = imp.base.add(0x3D4C17);
const producerAfter = imp.base.add(0x3D4C1A);

let activeThreads = {};
let pending = {};

console.log("FUNCTION START :", functionStart);
console.log("PRODUCER CALL  :", producerCall);
console.log("AFTER CALL     :", producerAfter);

Interceptor.attach(functionStart, {
    onEnter(args) {
        const tid = this.threadId;

        if (activeThreads[tid])
            return;

        activeThreads[tid] = true;

        send({
            event: "function_enter",
            thread: tid
        });

        Stalker.follow(tid, {
            transform(iterator) {
                let insn;

                while ((insn = iterator.next()) !== null) {

                    if (insn.address.equals(producerCall)) {

                        iterator.putCallout(function (context) {
                            const target = context.r9;
                            const buffer = context.rdi;
                            const object = context.rsi;
                            const size = context.rbx.toUInt32();

                            let vt = ptr(0);

                            try {
                                vt = object.readPointer();
                            } catch (e) {}

                            pending[tid] = {
                                target: target,
                                buffer: buffer,
                                object: object,
                                size: size
                            };

                            send({
                                event: "before",
                                thread: tid,
                                target: target.toString(),
                                symbol: DebugSymbol.fromAddress(
                                    target
                                ).toString(),
                                object: object.toString(),
                                vtable: vt.toString(),
                                buffer: buffer.toString(),
                                size: size
                            });
                        });
                    }

                    if (insn.address.equals(producerAfter)) {

                        iterator.putCallout(function (context) {
                            const p = pending[tid];

                            if (!p)
                                return;

                            let head = "";

                            try {
                                const n = Math.min(
                                    p.size,
                                    64
                                );

                                const ab = p.buffer.readByteArray(n);
                                const arr = new Uint8Array(ab);

                                head = Array.from(arr)
                                    .map(
                                        x => x
                                            .toString(16)
                                            .padStart(2, "0")
                                    )
                                    .join(" ");

                            } catch (e) {
                                head = "<READ ERROR: " + e + ">";
                            }

                            send({
                                event: "after",
                                thread: tid,
                                target: p.target.toString(),
                                buffer: p.buffer.toString(),
                                size: p.size,
                                head: head
                            });

                            delete pending[tid];
                        });
                    }

                    iterator.keep();
                }
            }
        });
    },

    onLeave(retval) {
        const tid = this.threadId;

        if (!activeThreads[tid])
            return;

        Stalker.unfollow(tid);

        delete activeThreads[tid];

        send({
            event: "function_leave",
            thread: tid
        });
    }
});

send({
    event: "ready"
});
'''

script = session.create_script(js)

def on_message(message, data):
    if message["type"] == "error":
        print("\nFRIDA ERROR:")
        print(message.get("stack", message))
        return

    p = message.get("payload", {})
    event = p.get("event")

    if event == "ready":
        print("\nHOOK READY")
        print("Сделай изменение дизайна и Ctrl+S.")
        print("PowerShell не трогай, он слушает 60 секунд.\n")

    elif event == "function_enter":
        print(
            f"[FUNCTION ENTER] thread={p['thread']}"
        )

    elif event == "before":
        print("\n=== PRODUCER CALL ===")
        print("TARGET :", p["target"])
        print("SYMBOL :", p["symbol"])
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

    elif event == "function_leave":
        print(
            f"[FUNCTION LEAVE] thread={p['thread']}"
        )

script.on("message", on_message)
script.load()

time.sleep(60)

script.unload()
session.detach()
