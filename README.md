# YouTube Digest

A Python script that turns the latest videos from YouTube channels you follow into a short email digest, so you get the key ideas without watching every video.

## How the pipeline works
1. Finds each tracked channel's newest upload through the YouTube Data API.
2. Extracts the video's English transcript, preferring human-written captions over auto-generated ones.
3. Sends the transcript to Claude with a structured prompt that returns a three-sentence summary and four to five takeaways.
4. Emails everything as one HTML digest through Gmail SMTP, with thumbnails and links.
5. Records processed video IDs in `seen_videos.json` so nothing repeats. IDs are saved only after the email sends, so a failed send is retried on the next run.

## Details
- Reads each channel's uploads playlist instead of using search, which is more reliable
- Skips videos of 3 minutes or less, such as Shorts
- Takes the newest unseen video with an English transcript from each channel per run
- Videos without English captions are skipped

## Setup
1. Install the dependencies:
```bash
   pip install -r requirements.txt
```
2. Copy `.env.example` to `.env` and fill in your values:
   - `DEVELOPER_KEY`: a YouTube Data API key from Google Cloud Console
   - `ANTHROPIC_KEY`: your Anthropic API key
   - `SENDER_EMAIL` and `RECIPIENT_EMAIL`: Gmail address(es)
   - `GMAIL_APP_PASSWORD`: a Gmail app password (requires 2-step verification)
3. Edit `uploads_playlist_ids` in `main.py` to list your channels. A channel's uploads playlist ID is its channel ID with the leading `UC` replaced by `UU`.
4. Run it:
```bash
   python main.py
```

To run it on a schedule, use cron or macOS launchd.

## Notes
- Built in spring 2026 and published to GitHub in October 2026.
- Each run calls the Anthropic API, which is a paid service.
- Never commit your `.env` file. It is listed in `.gitignore`.