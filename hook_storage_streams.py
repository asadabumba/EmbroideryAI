import frida
import psutil

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

const saveProps = imp.base.add(0x597D50); 
// RVA = 0x3F67D50 - Import base 0x39D0000 = 0x597D50

let hookedCreate = new Set();
let hookedOpen = new Set();

function hookStorage(storage) {
    if (storage.isNull())
        return;

    let vt;

    try {
        vt = storage.readPointer();
    } catch (e) {
        return;
    }

    const createStream = vt.add(3 * Process.pointerSize).readPointer();
    const openStream   = vt.add(4 * Process.pointerSize).readPointer();

    const createKey = createStream.toString();
    const openKey = openStream.toString();

    if (!hookedCreate.has(createKey)) {
        hookedCreate.add(createKey);

        console.log(
            "[HOOK CreateStream] " + createStream
        );

        Interceptor.attach(createStream, {
            onEnter(args) {
                this.name = "<unreadable>";

                try {
                    this.name = args[1].readUtf16String();
                } catch (e) {}

                console.log(
                    "[CreateStream] \"" +
                    this.name +
                    "\" mode=0x" +
                    args[2].toUInt32().toString(16)
                );
            },

            onLeave(retval) {
                console.log(
                    "    -> HRESULT=" + retval
                );
            }
        });
    }

    if (!hookedOpen.has(openKey)) {
        hookedOpen.add(openKey);

        console.log(
            "[HOOK OpenStream] " + openStream
        );

        Interceptor.attach(openStream, {
            onEnter(args) {
                this.name = "<unreadable>";

                try {
                    this.name = args[1].readUtf16String();
                } catch (e) {}

                console.log(
                    "[OpenStream] \"" +
                    this.name +
                    "\""
                );
            },

            onLeave(retval) {
                console.log(
                    "    -> HRESULT=" + retval
                );
            }
        });
    }
}

Interceptor.attach(saveProps, {
    onEnter(args) {
        console.log("\n[SAVE PROPERTY INFORMATION]");

        console.log(
            "IStorage*       = " + args[0]
        );

        console.log(
            "DesignDocument = " + args[1]
        );

        console.log(
            "arg3           = 0x" +
            args[2].toUInt32().toString(16)
        );

        hookStorage(args[0]);
    },

    onLeave(retval) {
        console.log(
            "[SAVE PROPERTY INFORMATION END] ret=" +
            retval
        );
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

    payload = message.get("payload", {})

    if payload.get("event") == "ready":
        print("\nHOOK READY")
        print("Сделай реальное изменение EMB и один Ctrl+S.")
        print("После сохранения вернись сюда и нажми Enter.\n")

script.on("message", on_message)
script.load()

input()

script.unload()
session.detach()
