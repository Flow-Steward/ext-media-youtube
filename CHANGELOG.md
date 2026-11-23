# Changelog

## 0.1.0 — 2026-11-23

First release, built on the Discovery documents of the YouTube Data API v3 (revision 20261119, SHA-256 `011818b42508629448e4839de27972272b86048d391e85b875447e85e563a316`) and the YouTube Analytics API v2 (revision 20261122, SHA-256 `996070e3d35b892e1809ce35484fbaf35b65e5d9f842346aec8626109eaf7e60`), downloaded 2026-11-23.

- 89 of the 91 methods of the two APIs are steps: channels, videos, playlists, comments, captions, live streaming, subscriptions, and analytics groups and reports. The two left out, and why, are on the Coverage page.
- Everyday steps: Test connection, Get my channels, Get all channel videos, Get videos by ID, Upload video, Get video processing status, Update video details, Set video thumbnail, Get all video comments, Reply to comment, Get all my playlists, Create playlist, Add video to playlist and Get analytics report.
- Connections are YouTube channels authorized through your own Google Cloud OAuth client; Flow Steward keeps and renews the authorization. Three connection types ask for different Google scopes.
- Files are uploaded from workflow files with YouTube's resumable upload; an uploaded video returns processing `accepted` until YouTube has processed it.
- List steps read all pages with an exact continuation token. Each Data API step names its quota cost from YouTube's quota table.
- Changes are sent once and never retried automatically; test runs never send them. Analytics numbers are exact decimals.
