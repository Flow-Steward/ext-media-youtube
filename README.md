# YouTube integration for Flow Steward

<img src="icon.png" width="96" alt="YouTube integration for Flow Steward">

[![CI](https://img.shields.io/github/actions/workflow/status/Flow-Steward/ext-media-youtube/ci.yml?branch=main&label=CI)](https://github.com/Flow-Steward/ext-media-youtube/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/Flow-Steward/ext-media-youtube?label=release)](https://github.com/Flow-Steward/ext-media-youtube/releases/latest)

Automate your YouTube channel with Flow Steward workflows and AI agents: upload videos, keep titles and playlists in order, answer comments and moderate live chats — without writing code.

This Flow Steward extension is a YouTube integration for video publishing and channel management. It works through the YouTube Data API v3, uploads videos from workflow files, follows their processing, reads all comments and videos of a channel and makes the methods of the API available for workflow automation.

## What is this

YouTube is Google's video platform. This extension is a connector: it adds ready YouTube steps to the Flow Steward workflow editor and the same operations as tools for AI agents. Read more about Flow Steward at <https://docs.flowsteward.org>.

## What you can automate

- Publish a video produced in an earlier step: upload it as private, set its thumbnail, schedule its publication and add it to a playlist.
- Keep video titles, descriptions and tags in line with your catalog or campaign plan.
- Collect all new comments of your videos for a support or community team, and reply from a workflow after review.
- Export the list of all videos of a channel with their statistics to a spreadsheet or BI tool.
- Manage live broadcasts, live chat moderation, captions and channel sections.

## Why teams use it

- **Uploads from workflow files.** A video, thumbnail, banner or caption track produced earlier in the workflow is uploaded with YouTube's resumable upload; nothing is created before the last byte arrives.
- **Uploaded is not mistaken for processed.** Upload video returns the new video ID with `processing` `accepted`; **Get video processing status** says when YouTube has finished with it.
- **Changes are not lost or doubled.** A step that changes data is never retried automatically. When its outcome is unclear (a lost answer, a server error) it says so, and you check YouTube before running it again.
- **Lists are read to the end.** Videos, comments, playlists and every other list are read page after page; when a step stops early it returns the exact token to continue from.
- **Quota in view.** Each step names its cost in YouTube quota units; a used-up quota is reported as such.
- **A test run changes nothing.** Writes are declared external effects, and Flow Steward suppresses them in test runs.
- **Tokens stay secret.** Flow Steward keeps and renews the Google authorization; a step receives only the current access token and removes it from every answer.

## What's inside

Everyday steps:

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

81 of the 83 methods of the YouTube Data API v3 are also available as steps: channels, videos, playlists, comments, captions, live streaming and subscriptions. The extension's **Coverage** page lists the two methods without a step and why.

YouTube Analytics reports are in the separate extension [YouTube Analytics](https://github.com/Flow-Steward/ext-marketing-youtube-analytics) (`flowsteward.youtube-analytics`).

## Get started

1. In Flow Steward, open **Extensions → Catalog**, find **YouTube** and install it.
2. In Google Cloud, enable **YouTube Data API v3**, configure the OAuth consent screen and create an OAuth client of the type **Web application**. Add the OAuth Redirect URI shown on the extension's **Connection** page as an authorized redirect URI.
3. On the **Connection** page, enter the client's **Client ID** and **Client Secret**, choose a connection type, press **Connect**, sign in with the channel's Google account and allow the access. Then press **Test connection**.
4. Build your first workflow: for example, a video file from an earlier step → **Upload video** → **Get video processing status** later → **Add video to playlist**.

## Requirements

- A YouTube channel and its Google account.
- A Google Cloud project with YouTube Data API v3 enabled and an OAuth client of the type Web application; its Client ID and Client Secret are entered on the Connection page. Whether Google must verify the app follows Google's policies for the scopes it asks for.
- The connection type with the scopes your steps need: **YouTube channel** (`youtube.force-ssl`), **YouTube channel with memberships** (adds `youtube.channel-memberships.creator` for channel members) or **YouTube content owner** (for YouTube partners' CMS accounts).
- YouTube quota: every request counts against the daily quota of your Google Cloud project; each step names its cost.
- A video uploaded from a workflow file can be up to 200 MiB, the size Flow Steward allows for a workflow file by default (YouTube itself takes up to 256 GiB).
- Flow Steward 0.9.23 or later.

## FAQ

**How do I upload a video to YouTube from a workflow?**
Pass the video file from an earlier step to **Upload video** with its title and privacy. The step returns the new video ID; YouTube then processes the video, and **Get video processing status** tells you when it is done.

**How do I export all videos of my YouTube channel?**
Run **Get all channel videos**, with `output` `file` for a long list, then **Get videos by ID** for their statistics.

**Can I answer YouTube comments automatically?**
Read new comments with **Get all video comments**, let an agent or a person prepare the answer, and post it with **Reply to comment**.

**What happens when the YouTube quota is used up?**
YouTube refuses the request with `quotaExceeded`; the step fails with `rate_limited`, says that the quota is used up and changes nothing.

**Can I try the YouTube integration without touching my channel?**
Yes. A test run of a workflow never sends changes; reads run as usual.

## In your language

Интеграция YouTube с Flow Steward автоматизирует работу канала без программирования: загрузка видео из файла workflow, обновление названий и описаний, плейлисты и ответы на комментарии. 81 из 83 методов YouTube Data API v3 доступен как шаг workflow; отчёты YouTube Analytics — в отдельном расширении YouTube Analytics. Для подключения нужен собственный OAuth-клиент Google Cloud (Client ID и Client Secret).

## Links

- Flow Steward documentation: <https://docs.flowsteward.org>
- Flow Steward extension catalog: <https://github.com/Flow-Steward/extensions>
- Issues and support: <https://github.com/Flow-Steward/ext-media-youtube/issues>
- YouTube Data API documentation: <https://developers.google.com/youtube/v3>
- YouTube Analytics extension: <https://github.com/Flow-Steward/ext-marketing-youtube-analytics>
- Changes: [CHANGELOG.md](CHANGELOG.md)

## For developers

Every step is generated from the Discovery document pinned in `tests/reference/` (`youtube_v3.json`, revision 20261119, downloaded 2026-11-23) and from the quota table extracted from YouTube's documentation (`tests/reference/quota_costs.json`). To rebuild the contracts:

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
