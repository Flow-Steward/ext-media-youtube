# Changelog

## 0.1.0 — 2026-11-23

First release, built on the Discovery document of the YouTube Data API v3 (revision 20261119, SHA-256 `011818b42508629448e4839de27972272b86048d391e85b875447e85e563a316`), downloaded 2026-11-23.

- 81 of the 83 methods of the API are steps: channels, videos, playlists, comments, captions, live streaming and subscriptions. The two left out, and why, are on the Coverage page.
- YouTube Analytics reports are in the separate extension [YouTube Analytics](https://github.com/Flow-Steward/ext-marketing-youtube-analytics) (`flowsteward.youtube-analytics`).
- Everyday steps: Test connection, Get my channels, Get all channel videos, Get videos by ID, Upload video, Get video processing status, Update video details, Set video thumbnail, Get all video comments, Reply to comment, Get all my playlists, Create playlist and Add video to playlist.
- Connections are YouTube channels authorized through your own Google Cloud OAuth client; Flow Steward keeps and renews the authorization. Three connection types ask for different Google scopes.
- Files are uploaded from workflow files with YouTube's resumable upload; an uploaded video returns processing `accepted` until YouTube has processed it.
- List steps read all pages with an exact continuation token. Each Data API step names its quota cost from YouTube's quota table.
- Changes are sent once and never retried automatically; test runs never send them.
