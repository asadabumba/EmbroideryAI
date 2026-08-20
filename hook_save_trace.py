import frida
import psutil

pid = next(
    p.info["pid"]
    for p in psutil.process_iter(["pid", "name"])
    if (p.info["name"] or "").lower() == "es.exe"
)

session = frida.attach(pid)

js = r'''
const interesting = [
    "ArchiveEmbedded",
    "SavePropertyInformation",
    "WriteDesignProperties",
    "WriteDrawingFile",
    "WriteTapeFile",
    "SaveAsLatestART"
];

let hooked = 0;

for (const mod of Process.enumerateModules()) {
    let exports;

    try {
        exports = mod.enumerateExports();
    } catch (e) {
        continue;
    }

    for (const exp of exports) {
        if (exp.type !== "function")
            continue;

        const match = interesting.some(
            x => exp.name.indexOf(x) !== -1
        );

        if (!match)
            continue;

        console.log(
            "[HOOK] " +
            mod.name +
            "!" +
            exp.name +
            " @ " +
            exp.address
        );

        try {
            Interceptor.attach(exp.address, {
                onEnter(args) {
                    send({
                        event: "hit",
                        module: mod.name,
                        name: exp.name,
                        address: exp.address.toString(),
                        thread: this.threadId
                    });
                }
            });

            hooked++;
        } catch (e) {
            console.log(
                "[FAILED] " +
                mod.name +
                "!" +
                exp.name +
                " : " +
                e
            );
        }
    }
}

send({
    event: "ready",
    hooked: hooked
});
'''

script = session.create_script(js)

def on_message(message, data):
    if message["type"] == "error":
        print(message.get("stack", message))
        return

    p = message.get("payload", {})

    if p.get("event") == "ready":
        print("\nHOOK READY")
        print("HOOKED:", p["hooked"])
        print(
            "Теперь сделай реальное изменение в EMB "
            "и нажми Ctrl+S."
        )
        print(
            "После сохранения вернись сюда и нажми Enter.\n"
        )

    elif p.get("event") == "hit":
        print(
            "[HIT] "
            + p["module"]
            + "!"
            + p["name"]
        )

script.on("message", on_message)
script.load()

input()

script.unload()
session.detach()
