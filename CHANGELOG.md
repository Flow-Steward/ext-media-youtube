# Changelog

## 0.1.2 — 2026-11-24

- Every input has one readable label in every step; inputs that mean the same are described the same.
- New pages: a detailed Setup Guide (Google Cloud project, consent screen, OAuth client, connecting a channel, connection types, quota, uploads, errors), one page per connection type, and YouTube API coverage with every step's YouTube method, quota cost, inputs, body fields and returned fields, generated from the pinned Discovery document.
- A detailed README with what you can automate.

## 0.1.1 — 2026-11-24

- The tests check the install folder from the extension id, not the checkout folder, so they pass in the repository's own checkout (v0.1.0 was tagged, but its release did not build).

## 0.1.0 — 2026-11-23

First release, built on the Discovery document of the YouTube Data API v3 (revision 20261119, SHA-256 `011818b42508629448e4839de27972272b86048d391e85b875447e85e563a316`), downloaded 2026-11-23.

- 81 of the 83 methods of the API are steps: channels, videos, playlists, comments, captions, live streaming and subscriptions. The two left out, and why, are on the Coverage page.
- YouTube Analytics reports are in the separate extension [YouTube Analytics](https://github.com/Flow-Steward/ext-marketing-youtube-analytics) (`flowsteward.youtube-analytics`).
- Everyday steps: Test connection, Get my channels, Get all channel videos, Get videos by ID, Upload video, Get video processing status, Update video details, Set video thumbnail, Get all video comments, Reply to comment, Get all my playlists, Create playlist and Add video to playlist.
- Connections are YouTube channels authorized through your own Google Cloud OAuth client; Flow Steward keeps and renews the authorization. Three connection types ask for different Google scopes.
- Files are uploaded from workflow files with YouTube's resumable upload; an uploaded video returns processing `accepted` until YouTube has processed it.
- List steps read all pages with an exact continuation token. Each Data API step names its quota cost from YouTube's quota table.
- Changes are sent once and never retried automatically; test runs never send them.
- An answer cut off before its end (fewer bytes than Content-Length, or a chunked answer that stops early) is never taken for a whole one: a read fails with `invalid_response`, a change YouTube confirmed returns without data and with a warning, a creation says it was made but its id is not known, and a caption file is not saved. An empty answer where JSON is documented is `invalid_response`.
- Each step offers only the connection types whose Google scopes allow its methods: the channel members and membership levels steps need the YouTube channel with memberships connection.
- Posts (`posts.*`) are not included: they are not in the Discovery document and Google opens them only to approved launch partners; see the Coverage page.
- A video, thumbnail or caption file is streamed from Flow Steward storage to a temporary file and uploaded part by part: about one 8 MiB part is in memory, not the whole file.
- A caption download answered with an empty body fails with `invalid_response` instead of returning no file.
- A list never returns more records than asked for: when YouTube answers more, the rest of that page is left for the next run, which starts from `next_page_token` and `skip` (`next_skip`).
