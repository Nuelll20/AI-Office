from . import db


def emit(actor, action, text="", target=None, video_id=None):
    """action: walk_to | back | work | say
    UI kantor membaca tabel ini dan menganimasikannya."""
    import time
    db.run("INSERT INTO events(ts,actor,target,action,text,video_id) VALUES(?,?,?,?,?,?)",
           (time.time(), actor, target, action, text, video_id))
    arrow = f" -> {target}" if target else ""
    print(f"[{actor}{arrow}] {action}: {text}")
