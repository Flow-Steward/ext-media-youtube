# YouTube integration for Flow Steward

<img src="icon.png" width="96" alt="YouTube integration for Flow Steward">

[![CI](https://img.shields.io/github/actions/workflow/status/Flow-Steward/ext-media-youtube/ci.yml?branch=main&label=CI)](https://github.com/Flow-Steward/ext-media-youtube/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/Flow-Steward/ext-media-youtube?label=release)](https://github.com/Flow-Steward/ext-media-youtube/releases/latest)
[![YouTube Data API](https://img.shields.io/badge/YouTube%20Data%20API-v3-FF0000)](https://developers.google.com/youtube/v3)
[![Steps](https://img.shields.io/badge/steps-94-blue)](#whats-inside)

Automate your YouTube channel with Flow Steward workflows and AI agents — no code. Upload videos from earlier workflow steps and follow their processing, keep titles, descriptions, thumbnails and playlists in order, answer comments, moderate live chats and export everything your channel holds.

The extension works through the YouTube Data API v3 and your own Google Cloud OAuth client. 81 methods of the API are workflow steps of their own, and 13 everyday steps cover the common jobs: 94 steps in all.

## What is this

[YouTube](https://www.youtube.com) is Google's video platform. [Flow Steward](https://docs.flowsteward.org) runs workflows and AI agents that connect business systems.

This extension connects the two. Once installed, YouTube appears in the Flow Steward workflow editor as a set of steps, and the same operations are available to AI agents as tools. Each connection is one YouTube channel, authorized by its owner through Google's own sign-in page; Flow Steward keeps the authorization, renews it and never shows it again.

Channel and video reports — views, watch time, audience, revenue — come from the companion extension [YouTube Analytics](https://github.com/Flow-Steward/ext-marketing-youtube-analytics).

## What you can automate

### Publishing

- **Publish from your production pipeline.** When a video is rendered or exported, upload it from the workflow file as private, set its custom thumbnail, add it to the right playlists and schedule the moment it goes public.
- **Wait for processing before the next step.** **Upload video** returns the new video ID at once; **Get video processing status** says when YouTube has finished, so a workflow only shares the link of a video that plays.
- **Captions in every language.** Upload caption tracks produced by a transcription or translation step, and download existing tracks for review.
- **Channel branding.** Upload a channel banner, set or remove the channel watermark, and arrange channel sections.

### Catalog and metadata

- **Titles and descriptions in line with your catalog.** Update titles, descriptions, tags, categories and publishing times from a product catalog, a campaign plan or a spreadsheet; fields you do not give stay as they are.
- **Playlists that keep themselves.** Create playlists for each series, product or season, add new videos in order and remove old ones.
- **Complete channel exports.** Read every video of a channel through its uploads playlist — into the step output or a JSON file — and every video's details and statistics, 50 per request, for a spreadsheet or BI tool.

### Community

- **Comment inbox for your team.** Collect all new comments of your videos with their replies and hand them to a support or community team, or to an AI agent that drafts answers.
- **Reply from a workflow.** Post a reviewed answer as the channel with **Reply to comment**.
- **Moderation.** Hold, publish or reject comments, mark spam, and ban authors.
- **Live streams.** Create live broadcasts and streams, bind them, move a broadcast through testing, live and complete, insert cue points, and moderate the live chat — send and delete messages, add moderators, ban users, read Super Chat events.

### Channel management

- **Memberships.** Read the channel's members and membership levels (with the **YouTube channel with memberships** connection).
- **Subscriptions.** Read, add and remove the channel's subscriptions.
- **Search.** Search YouTube for videos, channels and playlists with every filter of the API.

## Why teams use it

- **Uploads from workflow files.** Videos, thumbnails, banners, playlist images and caption tracks produced earlier in the workflow are sent with YouTube's resumable upload, in parts of 8 MiB, so only one part is in memory. YouTube creates nothing before the last byte arrives.
- **Uploaded is not mistaken for processed.** **Upload video** returns `processing: accepted`; **Get video processing status** says when YouTube is done.
- **Changes are sent once.** A step that changes data is never retried automatically. When its outcome is unclear — an answer lost on the way, a server error — it says so, and you look at YouTube before running it again.
- **Lists are read to the end.** Videos, comments, playlists and every other list are read page after page, and a result never holds more than asked for. When a step stops early it returns the exact place to continue from.
- **Quota in view.** Each step names its cost in YouTube quota units from YouTube's own quota table; a used-up quota is reported as such and changes nothing.
- **The right connection for each step.** Every step names the Google scopes that allow it and offers only the connection types that have them.
- **Test runs change nothing.** Every change is a declared external effect, suppressed in test runs.
- **Tokens stay secret.** A step receives only the current access token and removes it from every answer, warning and error.

## What's inside

### Everyday steps

- **Test connection** — checks the authorization and returns the channel.
- **Get my channels** — the channels of the connected account with their statistics.
- **Get all channel videos** — every video of a channel through its uploads playlist, into the step output or a JSON file.
- **Get videos by ID** — details and statistics of many videos, 50 per request.
- **Upload video** — a video from a workflow file with title, description, tags, category and privacy.
- **Get video processing status** — how far YouTube got with an uploaded video.
- **Update video details** — title, description, tags, category, privacy, publishing time; the fields not given stay as they are.
- **Set video thumbnail** — a custom thumbnail from a workflow file.
- **Get all video comments** — every comment thread of a video, with replies if asked.
- **Reply to comment** — answer a comment as the channel.
- **Get all my playlists**, **Create playlist**, **Add video to playlist**.

### YouTube Data API steps by area

- **Channels** (16 steps) — channels, channel sections, activities, members and membership levels, banners, watermarks and third-party links. Examples: **Get channels**, **Update channel**, **Get channel members**, **Upload channel banner**.
- **Videos** (14 steps) — videos, ratings, categories, search, abuse reports, thumbnails and uploads. Examples: **Get videos**, **Update video**, **Upload video file**, **Search YouTube**.
- **Playlists** (12 steps) — playlists, their items and images. Examples: **Get playlist items**, **Create playlist item**, **Update playlist**.
- **Comments and captions** (13 steps) — comment threads, comments and their moderation, caption tracks. Examples: **Get comment threads**, **Set comment moderation status**, **Upload caption track**.
- **Live streaming** (21 steps) — broadcasts, streams, live chat, moderators, bans and Super Chat events. Examples: **Create live broadcast**, **Change live broadcast status**, **Send live chat message**.
- **Subscriptions and regions** (5 steps) — subscriptions, content regions and interface languages. Examples: **Get subscriptions**, **Create subscription**.

The **YouTube API coverage** page of the installed extension lists every step with the YouTube method it calls, its quota cost, its inputs, the fields of its request body and the fields YouTube returns.

### Pages in Flow Steward

- **Setup Guide** — the Google Cloud project, consent screen, OAuth client, quota and errors.
- **Connection**, **Connection with memberships**, **Content owner connection** — one page per connection type.
- **YouTube API** and one page per area — every step with what it does.
- **YouTube API coverage**, **Changelog**, **Support**.

## Get started

1. **Install the extension.** In Flow Steward open **Extensions → Catalog**, find **YouTube** and install it.
2. **Set up Google Cloud.** Enable **YouTube Data API v3**, configure the OAuth consent screen with the scope `youtube.force-ssl`, and create an OAuth client of the type **Web application** with the **OAuth Redirect URI** from the extension's **Connection** page.
3. **Enter the client.** On the **Connection** page enter the **Client ID** and **Client Secret** and save them.
4. **Connect the channel.** Press **Connect**, sign in with the channel's Google account, choose the channel and allow the access. Press **Test connection**.
5. **Build your first workflow.** For example: *a video file from an earlier step* → **Upload video** → *later* **Get video processing status** → **Add video to playlist**.

The **Setup Guide** page of the extension walks through every screen.

## Requirements

- **A YouTube channel** and the Google account that owns or manages it.
- **A Google Cloud project** with YouTube Data API v3 enabled and an OAuth client of the type Web application. Whether Google must verify the app follows Google's policies for the scopes it asks for. An external app in **Testing** receives refresh tokens that expire in 7 days; publish it for lasting connections.
- **The connection type with the scopes your steps need:** **YouTube channel** (`youtube.force-ssl`), **YouTube channel with memberships** (adds `youtube.channel-memberships.creator`) or **YouTube content owner** (adds `youtubepartner` and `youtubepartner-channel-audit` for partners' CMS accounts).
- **YouTube quota.** Every request counts against your project's daily quota. Google's getting-started guide gives a default allocation of 100 `search.list` calls, 100 `videos.insert` calls and 10,000 units per day for all other endpoints; each step names its cost.
- **File sizes.** A workflow file read by a step is up to 200 MiB, the size Flow Steward allows by default; YouTube accepts videos up to 256 GiB.
- **Flow Steward** 0.9.23 or later.

## FAQ

**How do I upload a video to YouTube from a workflow?**
Pass the video file from an earlier step to **Upload video** with its title and privacy. The step returns the new video ID; YouTube then processes the video, and **Get video processing status** tells you when it is done.

**Is an uploaded video public right away?**
No. **Upload video** makes it private unless you choose otherwise. Set `publish_at` to schedule the moment it goes public, or change the privacy later with **Update video details**.

**How do I export all videos of my YouTube channel?**
Run **Get all channel videos**, with `output` `file` for a long list, then **Get videos by ID** for their statistics.

**Can I answer YouTube comments automatically?**
Read new comments with **Get all video comments**, let an agent or a person prepare the answer, and post it with **Reply to comment**.

**How do I read channel members?**
Use the **Connection with memberships** page to connect the channel, then run **Get channel members**. The channel needs memberships turned on in YouTube Studio.

**What happens when the YouTube quota is used up?**
YouTube refuses the request with `quotaExceeded`; the step fails with `rate_limited`, says that the quota is used up and changes nothing. The quota renews daily.

**Why does my connection stop working after a week?**
The OAuth consent screen is in **Testing**, where Google issues refresh tokens that expire in 7 days. Publish the app, then connect again.

**Can I try the YouTube integration without touching my channel?**
Yes. A test run of a workflow never sends changes; reads run as usual.

**Where are views, watch time and revenue?**
In the companion extension [YouTube Analytics](https://github.com/Flow-Steward/ext-marketing-youtube-analytics), which reads YouTube Analytics reports for the same channel.

## In your language

**Русский.** Интеграция YouTube для Flow Steward автоматизирует работу канала без программирования: загрузка видео из файла workflow с отслеживанием обработки, названия, описания, обложки и плейлисты, ответы на комментарии, модерация прямых эфиров и полная выгрузка видео канала. 81 метод YouTube Data API v3 доступен как шаг workflow, плюс повседневные шаги. Для подключения нужен собственный OAuth-клиент Google Cloud.

**Deutsch.** Die YouTube-Integration für Flow Steward automatisiert Ihren Kanal ohne Programmierung: Videos aus Workflow-Dateien hochladen und ihre Verarbeitung verfolgen, Titel, Beschreibungen, Thumbnails und Playlists pflegen, Kommentare beantworten und Live-Chats moderieren. 81 Methoden der YouTube Data API v3 sind eigene Workflow-Schritte.

**Español.** La integración de YouTube para Flow Steward automatiza tu canal sin programar: sube vídeos desde archivos del workflow y sigue su procesamiento, mantiene títulos, descripciones, miniaturas y listas de reproducción, responde comentarios y modera chats en directo. 81 métodos de la YouTube Data API v3 son pasos de workflow propios.

**Français.** L'intégration YouTube pour Flow Steward automatise votre chaîne sans code : mise en ligne de vidéos depuis les fichiers du workflow avec suivi du traitement, titres, descriptions, miniatures et playlists, réponses aux commentaires et modération des chats en direct. 81 méthodes de la YouTube Data API v3 sont des étapes de workflow à part entière.

## Links

- Flow Steward documentation: <https://docs.flowsteward.org>
- Flow Steward extension catalog: <https://github.com/Flow-Steward/extensions>
- Issues and support: <https://github.com/Flow-Steward/ext-media-youtube/issues>
- YouTube Data API documentation: <https://developers.google.com/youtube/v3>
- YouTube Analytics extension: <https://github.com/Flow-Steward/ext-marketing-youtube-analytics>
- Changes: [CHANGELOG.md](CHANGELOG.md)

## For developers

Every step is generated from the Discovery document pinned in `tests/reference/` (`youtube_v3.json`, revision 20261119, downloaded 2026-11-23) and from the quota table extracted from YouTube's documentation (`tests/reference/quota_costs.json`). `tests/reference/field_texts.py` gives each input name one label in every step. To rebuild the contracts and the generated pages:

```bash
python3 tests/reference/build_contracts.py
```

To extract the quota table again, download `https://developers.google.com/youtube/data/determine_quota_cost?hl=en` to `tests/reference/sources/determine_quota_cost.html` (not committed) and run `python3 tests/reference/extract_quota.py`.

From a Flow Steward checkout (the checks run in the `fs-audit` container):

```bash
./core/entrypoints/cli/scripts/lint.sh --checks extension-static,extension-tests --extension-root "$PWD/workspace/extensions/flowsteward_youtube"
./flow-steward extensions validate flowsteward.youtube --root workspace/extensions --health --marketplace
./flow-steward extensions test flowsteward.youtube --root workspace/extensions
```

The read-only live test runs when `YOUTUBE_TOKEN_FILE` names a file with a current access token of a test channel; without it, it is skipped.

YouTube and the YouTube logo are trademarks of Google LLC; see [BRANDING.md](BRANDING.md) for the icon's source.
