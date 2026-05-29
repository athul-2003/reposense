# Demo

## Record the demo video

Install asciinema first:
```
pip install asciinema
```

Then record:
```
asciinema rec demo/demo.cast
./demo/demo.sh withcoral/coral 3
```

Play back before uploading:
```
asciinema play demo/demo.cast
```

## The wow moment
At the 1:10 mark, switch from withcoral/coral to django/django
live on screen. That moment — same command, different repo,
instant results — proves RepoSense is a real universal tool,
not a hardcoded demo. This is the single most important
moment in the entire video.

## Manual demo (interactive mode)
```
./run.sh --repo withcoral/coral
Type: "What should I work on today?"
Type: "Any security issues?"
Type: "Who contributed most this month?"
Type: "quit"
```

## Narration script
See [demo_script.md](demo_script.md) for the full 2-minute narration with
timings.
