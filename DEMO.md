# Demo guide

A 90-second video script, a rehearsal checklist, and what to rotate afterwards.

## Before you record: rehearsal checklist

Do this once, end to end, with no recording. Fix anything that fails, then record.

1. **Rotate keys first** (see the end of this file), then start fresh with `scripts/start.sh`.
2. **Tunnel** (only for remote viewers). In a second terminal: `cloudflared tunnel --url http://127.0.0.1:8766`. Copy the `https://…trycloudflare.com` address. Restart `scripts/start.sh` and paste it when asked. Restarting resets rooms, so do this before everything else.
3. **Streamer window** (http://127.0.0.1:8765): create a room, then **Prepare Twitch sign-in** and **Authorize on Twitch**. Your login name should appear.
4. **Enable `!draw`.** Status should say *listening*. If it does not, the server terminal prints the reason (`EventSub connection error` or `Twitch request failed`).
5. **OBS:** add a Browser Source with the OBS URL (1920 × 1080), put your webcam above it. Set the background to **Transparent** if you want objects over your webcam or game.
6. **Webcam preview:** turn it on in the streamer window and allow the camera. **Show only me** removes your room so the virtual background shows behind you. The first start loads the model (a second or two). Turn it off before OBS opens the camera, since one app may hold it. In OBS, use your webcam's background removal to get the same look on stream.
7. **Dry run:** type `!draw a neon cat` in your own chat. Approve it. Check that it shows in OBS. Open the viewer link on your phone and send one creation.

## 90-second video script

| Time | On screen | Say |
|---|---|---|
| 0:00 | Stream with webcam, empty scene | "This is Little Worlds. Chat builds the stream." |
| 0:08 | Type `!draw a smiling cloud wearing sunglasses` in Twitch chat | "A viewer doesn't need to leave Twitch. One chat command." |
| 0:15 | Streamer window: toast and chime, item appears in the review queue | "The streamer gets a private review queue. Nothing is public yet." |
| 0:22 | Click **Preview**, resize with the slider, drag into place, **Approve** | "They preview it on the scene, resize it, place it, and approve." |
| 0:32 | OBS: the cloud pops in with "Created by …" | "It appears on the stream, credited to the viewer." |
| 0:40 | Phone: open the viewer link, **Create from words** or draw a sketch, pick a style, **Preview with AI**, try again | "Viewers who want more can draw or describe, pick a style, and try again as often as they like, privately." |
| 0:55 | Choose **Part of the background** or **Full background**, send | "They can even propose a piece of the background." |
| 1:03 | Streamer: Backgrounds gallery, click a preset, then **From your stream**, then **Create with AI** with the 💡 helper | "The streamer has a background picker like a video call: presets, AI, upload, and everything chat made, ready to reuse. And if you don't know how to prompt, a helper asks four questions and writes it." |
| 1:15 | Show a moderation block (a flagged test prompt) or the warnings counter | "Everything is moderated, and nothing goes live without approval." |
| 1:22 | Hero shot of the OBS scene | "Chat builds the stream." |

Tips: record at 1080p, hide the terminal (it shows request lines), and keep the toast sound on. Plan one retake for the AI wait: the first AI preview takes 10 to 30 seconds, so trim it or narrate over it.

## After the hackathon: rotate and clean up

- **OpenAI key:** https://platform.openai.com/api-keys, delete the key you used, create a new one only if you need it.
- **Twitch secret:** https://dev.twitch.tv/console, open the app, **New Secret**.
- Keep `.venv/`, `.env` and anything with keys out of any repository (`.gitignore` already lists them).
- Set a monthly limit on the OpenAI account (Billing, Limits) and leave auto-reload off.
