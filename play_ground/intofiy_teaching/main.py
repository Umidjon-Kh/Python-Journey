from inotify_simple import INotify, flags

inotify = INotify()
wd = inotify.add_watch("/tmp", flags.CREATE | flags.CLOSE_WRITE | flags.DELETE)

print("Жду события в /tmp...")

while True:
    events = inotify.read()
    for event in events:
        event_flags = flags.from_mask(event.mask)
        for flag in event_flags:
            print(f"name={event.name} → {flag.name}")
