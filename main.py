import googleapiclient.discovery
import anthropic
import re
import json
import os
import smtplib
import html
from email.mime.text import MIMEText
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from datetime import date, datetime

# Loads API keys and email credentials from .env file
load_dotenv()
DEVELOPER_KEY = os.getenv("DEVELOPER_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# Uploads playlist is always accurate, used rather than search().list() since it is less reliable
uploads_playlist_ids = {
    "Alex Hormozi": "UUUyDOdBWhC1MCxEjC46d-zw",
    "Nate Herk | AI Automation": "UU2ojq-nuP8ceeHqiroeKhBA",
    "Jeff Nippard": "UU68TLK0mAEzUyHx5x5k-S1Q",
    "Matt Wolfe": "UUhpleBmo18P08aKCIgti38g",
    "Ali Abdaal": "UUoOae5nYA7VqaXzerajD0lg",
    "Isiah Rivera": 'UUw1mvHj6NL86Pj01IeBvjWA'
}

# API clients
youtube = googleapiclient.discovery.build(
    "youtube", "v3", developerKey=DEVELOPER_KEY)
claude = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Converts the duration of 
def parse_duration_seconds(iso_duration):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds):
    if seconds >= 3600:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h {mins}min"
    else:
        return f"{seconds // 60} min"


ytt_api = YouTubeTranscriptApi()

# Load deduplication log
seen_videos_path = "seen_videos.json"
if os.path.exists(seen_videos_path):
    with open(seen_videos_path) as f:
        seen_videos = set(json.load(f))
else:
    seen_videos = set()

# Stores transcripts as {title: {"channel": ..., "text": ...}}
transcripts = {}

for playlist in uploads_playlist_ids.values():
    next_page_token = None
    found = False
    while not found:
        playlist_response = youtube.playlistItems().list(
            part='contentDetails',
            playlistId=playlist,
            maxResults=10,
            pageToken=next_page_token
        ).execute()

        # Formats all the video ids in a single string separated by commas
        raw_ids = ','.join([item["contentDetails"]["videoId"] for item in playlist_response["items"]])

        videos_response = youtube.videos().list(
            part='snippet,contentDetails',
            id=raw_ids
        ).execute()

        for item in videos_response["items"]:
            duration_sec = parse_duration_seconds(item['contentDetails']['duration'])
            if duration_sec > 180:
                video_id = item["id"]
                title = item['snippet']['title']
                channel_name = item['snippet']['channelTitle']
                thumbnails = item['snippet']['thumbnails']
                thumbnail_url = thumbnails.get('high', thumbnails.get('medium', thumbnails['default']))['url']
                published_formatted = datetime.strptime(
                    item['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ'
                ).strftime('%B %d, %Y')
                duration_label = format_duration(duration_sec)
                if video_id in seen_videos:
                    print(f"Already up to date: {title}")
                    found = True
                    break
                try:
                    transcript_list = ytt_api.list(video_id)
                    try:
                        # Prefer manually created transcripts over auto-generated
                        transcript = transcript_list.find_manually_created_transcript(['en'])
                    except NoTranscriptFound:
                        transcript = transcript_list.find_generated_transcript(['en'])
                    fetched = transcript.fetch()
                    transcripts[title] = {
                        "channel": channel_name,
                        "video_id": video_id,
                        "text": "\n".join([chunk.text for chunk in fetched]),
                        "thumbnail": thumbnail_url,
                        "published": published_formatted,
                        "duration": duration_label
                    }
                    seen_videos.add(video_id)
                    print(f"Fetched transcript: {title}")
                    found = True
                    break
                except (TranscriptsDisabled, NoTranscriptFound):
                    print(f"Skipped (no English transcript available): {title}")

        if found:
            break
        next_page_token = playlist_response.get("nextPageToken")
        if not next_page_token:
            print(f"No transcript-available video found for playlist: {playlist}")
            break

print(f"\n{len(transcripts)} transcript(s) ready for summarization")


# Summarization of transcript 

summaries = {}

for title, data in transcripts.items():
    channel = data["channel"]
    transcript_text = data["text"]
    print(f"Summarizing: {title}...")

    response = claude.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1536,
        messages=[
            {
                "role": "user",
                "content": f"""You are generating one section of a YouTube digest, a scheduled, \
digestable newsletter that presents in a clear and concise manner the \
summary and key takeaways for the latest YouTube videos of channels the \
user wants to track. The goal is to save the user the time of getting \
trapped in the excess of information on YouTube and cycle of binge \
watching. Your job is to give the reader genuine value from this video \
without them having to watch it. Write as if you are a smart friend \
explaining it over a cup of coffee, rather than an academic who uses \
unnecessarily formal and convoluted language.

Here is the transcript of a YouTube video titled "{title}" from \
the channel "{channel}":

{transcript_text}

Produce exactly two sections using this format:

SUMMARY
Write exactly 3 sentences in plain, direct prose that together cover: \
what the video is about and why it matters, the central argument or \
narrative arc, and the broader takeaway — in whatever order flows most \
naturally. Again, avoid words that sound formal but add no information — \
words like 'throughline', 'nuanced', 'multifaceted', or 'paradigm'. \
That being said, do not oversimplify if that takes away from the \
understanding the user needs and desires for the video. If a technical \
term appears that a general reader might not know, concisely introduce \
its meaning or translate it in plain language — ex: 'background daemon' \
becomes 'always-on background process.' Do not use filler phrases like \
'the video explores' or 'this video discusses.'

KEY TAKEAWAYS
Write exactly 4-5 bullet points. Each bullet is a tight, punchy claim \
or fragment — specific and assertive, not vague or introductory. \
Order bullets roughly by impact — lead with the most surprising or \
actionable point. \
When a key figure makes the point more meaningful, include it — but pick \
one number, not a list: never 'investing early is important,' instead \
'starting 10 years earlier can lead to 340% more returns.' For opinion \
or narrative content, capture the core claim directly: never 'good \
systems help you think clearly,' instead 'most high-effort people \
underperform by optimizing outcomes instead of inputs.' Do not add a \
punchy em-dash conclusion at the end of bullets and try to avoid using \
too many em dashes in general. Name specific products, tools, \
books, or people when recommended.

Note: the transcript may be auto-generated and could contain errors. \
Use context to correct them silently — do not mention or explain \
transcript errors in the output. If you genuinely cannot determine the \
correct value, don't include it.

Return only the two sections — no preamble, no commentary, nothing \
before SUMMARY or after the last bullet point."""
            }
        ]
    )

    summaries[title] = response.content[0].text
    print(f"Summarized: {title}")

print(f"\n{len(summaries)} summary/summaries complete")


# Send HTML Email digest

def summary_to_html(title, channel, summary_text, video_id, thumbnail, published, duration):
    # Escape special characters to prevent broken HTML
    title_safe = html.escape(title)
    channel_safe = html.escape(channel)

    # Split Claude's response into SUMMARY and KEY TAKEAWAYS sections
    parts = re.split(r'\n+KEY TAKEAWAYS\n+', summary_text)
    summary_part = parts[0].replace('SUMMARY\n', '').strip()
    takeaways_part = parts[1].strip() if len(parts) > 1 else ''

    # Creates list of bullet strings
    bullets = [
        line.lstrip('-•').strip()
        for line in takeaways_part.split('\n')
        if line.strip().startswith(('-', '•'))
    ]
    bullets_html = '\n'.join(f'<li style="margin-bottom:8px;">{b}</li>' for b in bullets)
    yt_url = f"https://youtube.com/watch?v={video_id}"

    return f"""
    <div style="margin-bottom:40px; padding-bottom:30px; border-bottom:1px solid #e0e0e0; font-family:Georgia, serif;">
        <a href="{yt_url}">
            <img src="{thumbnail}" alt="{title_safe}" style="width:100%; max-width:480px; border-radius:6px; display:block; margin-bottom:14px;" />
        </a>
        <h2 style="color:#1a1a1a; margin-bottom:4px;">{title_safe}</h2>
        <p style="color:#888; font-size:13px; margin-top:0;">
            <strong>{channel_safe}</strong> &nbsp;·&nbsp; {published} &nbsp;·&nbsp; {duration}
        </p>
        <p style="line-height:1.8; color:#333;">{summary_part}</p>
        <ul style="line-height:1.8; color:#333; padding-left:20px;">
            {bullets_html}
        </ul>
        <a href="{yt_url}"
           style="display:inline-block; margin-top:12px; color:#ff0000; font-weight:bold; text-decoration:none;">
            ▶ Watch on YouTube
        </a>
    </div>
    """

if not summaries:
    print("No new videos found across all channels — digest not sent.")
else:
    today = date.today().strftime('%B %d, %Y')
    sections_html = ""
    for title, summary in summaries.items():
        channel = transcripts[title]["channel"]
        video_id = transcripts[title]["video_id"]
        sections_html += summary_to_html(
            title, channel, summary, video_id,
            transcripts[title]["thumbnail"],
            transcripts[title]["published"],
            transcripts[title]["duration"]
        )

    html_email = f"""
<!DOCTYPE html>
<html>
<body style="max-width:800px; margin:auto; padding:32px 24px; font-family:Georgia, serif; color:#1a1a1a;">
    <h1 style="font-size:26px; border-bottom:2px solid #1a1a1a; padding-bottom:12px;">
        YouTube Digest — {today}
    </h1>
    {sections_html}
    <p style="font-size:12px; color:#aaa; margin-top:40px;">Generated by YouTube Digest</p>
</body>
</html>
"""

    msg = MIMEText(html_email, 'html')
    msg['Subject'] = f"YouTube Digest — {today}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

    print("Digest emailed successfully")

    # Only mark videos as seen once the email has actually been sent
    with open(seen_videos_path, "w") as f:
        json.dump(list(seen_videos), f)
