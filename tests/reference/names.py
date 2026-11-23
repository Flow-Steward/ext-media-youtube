"""Titles, one-line summaries and areas of the generated steps.

Keyed by the method id of the pinned Discovery documents. The summary says in plain
words what the method does; build_contracts.py adds the facts of the source (quota
cost, scopes, paging, upload) to it.
"""

from __future__ import annotations

#: Method id -> (title, summary).
TITLES: dict[str, tuple[str, str]] = {
    # Channels
    "youtube.channels.list": (
        "Get channels",
        "Reads channels by ID, handle or username, or the channels of the connected account "
        "(mine).",
    ),
    "youtube.channels.update": (
        "Update channel",
        "Changes a channel's branding settings, localizations or status; the parts sent "
        "replace the current ones.",
    ),
    "youtube.channelSections.list": ("Get channel sections", "Reads the sections of a channel."),
    "youtube.channelSections.insert": (
        "Create channel section",
        "Adds a section to the connected channel.",
    ),
    "youtube.channelSections.update": (
        "Update channel section",
        "Changes a section of the connected channel.",
    ),
    "youtube.channelSections.delete": ("Delete channel section", "Removes a channel section."),
    "youtube.channelBanners.insert": (
        "Upload channel banner",
        "Uploads a banner image from a workflow file; set the URL it returns as the channel's "
        "banner with Update channel.",
    ),
    "youtube.watermarks.set": (
        "Set channel watermark",
        "Uploads a watermark image from a workflow file and sets it for a channel.",
    ),
    "youtube.watermarks.unset": ("Remove channel watermark", "Removes a channel's watermark."),
    "youtube.activities.list": (
        "Get channel activities",
        "Reads the activities of a channel or of the connected account.",
    ),
    "youtube.members.list": (
        "Get channel members",
        "Reads the members of the connected channel (channel memberships).",
    ),
    "youtube.membershipsLevels.list": (
        "Get membership levels",
        "Reads the membership levels the connected channel offers.",
    ),
    "youtube.thirdPartyLinks.list": (
        "Get third-party links",
        "Reads links between a channel and a store or affiliate program.",
    ),
    "youtube.thirdPartyLinks.insert": (
        "Create third-party link",
        "Links a channel with a store or affiliate program.",
    ),
    "youtube.thirdPartyLinks.update": (
        "Update third-party link",
        "Changes a link between a channel and a store or affiliate program.",
    ),
    "youtube.thirdPartyLinks.delete": (
        "Delete third-party link",
        "Removes a link between a channel and a store or affiliate program.",
    ),
    # Videos
    "youtube.videos.list": (
        "Get videos",
        "Reads videos by ID, or the videos the connected account rated, or the most popular "
        "videos of a region.",
    ),
    "youtube.videos.batchGetStats": (
        "Get video statistics batch",
        "Reads the statistics of up to 50 videos by ID.",
    ),
    "youtube.videos.getRating": (
        "Get my video ratings",
        "Reads the rating (like, dislike or none) the connected account gave to videos.",
    ),
    "youtube.videos.insert": (
        "Upload video file",
        "Uploads a video from a workflow file with its metadata in body, by YouTube's "
        "resumable upload.",
    ),
    "youtube.videos.update": (
        "Update video",
        "Changes a video's metadata; the parts sent replace the current ones, so fields left "
        "out of a part are cleared.",
    ),
    "youtube.videos.rate": ("Rate video", "Likes or dislikes a video, or removes the rating."),
    "youtube.videos.reportAbuse": ("Report video abuse", "Reports a video for abuse."),
    "youtube.videos.delete": ("Delete video", "Deletes a video."),
    "youtube.videoTrainability.get": (
        "Get video trainability",
        "Reads whether third parties may use a video for training.",
    ),
    "youtube.thumbnails.set": (
        "Set video thumbnail file",
        "Uploads a custom thumbnail image from a workflow file and sets it for a video.",
    ),
    "youtube.search.list": (
        "Search YouTube",
        "Searches videos, channels and playlists by keyword, location or channel.",
    ),
    "youtube.videoCategories.list": (
        "Get video categories",
        "Reads the video categories of a region or by ID.",
    ),
    "youtube.videoAbuseReportReasons.list": (
        "Get abuse report reasons",
        "Reads the reasons a video can be reported for.",
    ),
    "youtube.abuseReports.insert": ("Create abuse report", "Reports content for abuse."),
    # Playlists
    "youtube.playlists.list": (
        "Get playlists",
        "Reads playlists by ID, of a channel, or of the connected account.",
    ),
    "youtube.playlists.insert": ("Create playlist from body", "Creates a playlist."),
    "youtube.playlists.update": (
        "Update playlist",
        "Changes a playlist's title, description, privacy or localizations.",
    ),
    "youtube.playlists.delete": ("Delete playlist", "Deletes a playlist."),
    "youtube.playlistItems.list": (
        "Get playlist items",
        "Reads the items of a playlist, or items by ID.",
    ),
    "youtube.playlistItems.insert": (
        "Create playlist item",
        "Adds a video to a playlist.",
    ),
    "youtube.playlistItems.update": (
        "Update playlist item",
        "Changes a playlist item, for example its position.",
    ),
    "youtube.playlistItems.delete": ("Delete playlist item", "Removes an item from a playlist."),
    "youtube.playlistImages.list": (
        "Get playlist images",
        "Reads the cover images of a playlist.",
    ),
    "youtube.playlistImages.insert": (
        "Upload playlist image",
        "Uploads a playlist cover image from a workflow file.",
    ),
    "youtube.playlistImages.update": (
        "Update playlist image",
        "Changes a playlist cover image, optionally with a new image file.",
    ),
    "youtube.playlistImages.delete": ("Delete playlist image", "Removes a playlist cover image."),
    # Comments
    "youtube.commentThreads.list": (
        "Get comment threads",
        "Reads top-level comments with their first replies, of a video or a channel, or by ID.",
    ),
    "youtube.commentThreads.insert": (
        "Create comment thread",
        "Posts a new top-level comment.",
    ),
    "youtube.comments.list": (
        "Get comments",
        "Reads comments by ID, or the replies to a comment.",
    ),
    "youtube.comments.insert": (
        "Create comment reply",
        "Posts a reply to an existing comment.",
    ),
    "youtube.comments.update": ("Update comment", "Changes the text of a comment."),
    "youtube.comments.setModerationStatus": (
        "Set comment moderation status",
        "Publishes, holds for review or rejects comments, optionally banning the author.",
    ),
    "youtube.comments.markAsSpam": ("Mark comments as spam", "Flags comments as spam."),
    "youtube.comments.delete": ("Delete comment", "Deletes a comment."),
    # Captions
    "youtube.captions.list": ("Get caption tracks", "Reads the caption tracks of a video."),
    "youtube.captions.download": (
        "Download caption track",
        "Saves a caption track as a workflow file, optionally converted or translated.",
    ),
    "youtube.captions.insert": (
        "Upload caption track",
        "Uploads a caption track from a workflow file with its metadata in body.",
    ),
    "youtube.captions.update": (
        "Update caption track",
        "Changes a caption track's draft status, optionally with a new caption file.",
    ),
    "youtube.captions.delete": ("Delete caption track", "Deletes a caption track."),
    # Live
    "youtube.liveBroadcasts.list": (
        "Get live broadcasts",
        "Reads live broadcasts by ID, status or of the connected account.",
    ),
    "youtube.liveBroadcasts.insert": ("Create live broadcast", "Creates a live broadcast."),
    "youtube.liveBroadcasts.update": ("Update live broadcast", "Changes a live broadcast."),
    "youtube.liveBroadcasts.bind": (
        "Bind live broadcast to stream",
        "Binds a live broadcast to a video stream, or removes the binding.",
    ),
    "youtube.liveBroadcasts.transition": (
        "Change live broadcast status",
        "Moves a live broadcast to testing, live or complete.",
    ),
    "youtube.liveBroadcasts.insertCuepoint": (
        "Insert broadcast cuepoint",
        "Inserts a cuepoint (an ad break) into a live broadcast.",
    ),
    "youtube.liveBroadcasts.delete": ("Delete live broadcast", "Deletes a live broadcast."),
    "youtube.liveStreams.list": (
        "Get live streams",
        "Reads video streams by ID or of the connected account.",
    ),
    "youtube.liveStreams.insert": ("Create live stream", "Creates a video stream."),
    "youtube.liveStreams.update": ("Update live stream", "Changes a video stream."),
    "youtube.liveStreams.delete": ("Delete live stream", "Deletes a video stream."),
    "youtube.liveChatMessages.list": (
        "Get live chat messages",
        "Reads the messages of a live chat.",
    ),
    "youtube.liveChatMessages.insert": (
        "Send live chat message",
        "Posts a message to a live chat.",
    ),
    "youtube.liveChatMessages.transition": (
        "Change live chat event status",
        "Transitions a durable chat event, such as a poll.",
    ),
    "youtube.liveChatMessages.delete": (
        "Delete live chat message",
        "Deletes a live chat message.",
    ),
    "youtube.liveChatBans.insert": (
        "Ban live chat user",
        "Bans a user from a live chat, for a time or permanently.",
    ),
    "youtube.liveChatBans.delete": ("Remove live chat ban", "Lifts a live chat ban."),
    "youtube.liveChatModerators.list": (
        "Get live chat moderators",
        "Reads the moderators of a live chat.",
    ),
    "youtube.liveChatModerators.insert": (
        "Add live chat moderator",
        "Makes a user a moderator of a live chat.",
    ),
    "youtube.liveChatModerators.delete": (
        "Remove live chat moderator",
        "Removes a live chat moderator.",
    ),
    "youtube.superChatEvents.list": (
        "Get Super Chat events",
        "Reads the Super Chat and Super Sticker events of the connected channel.",
    ),
    # Subscriptions and reference data
    "youtube.subscriptions.list": (
        "Get subscriptions",
        "Reads subscriptions by ID, of a channel, of the connected account or its subscribers.",
    ),
    "youtube.subscriptions.insert": (
        "Create subscription",
        "Subscribes the connected account to a channel.",
    ),
    "youtube.subscriptions.delete": ("Delete subscription", "Unsubscribes from a channel."),
    "youtube.i18nLanguages.list": (
        "Get interface languages",
        "Reads the application languages YouTube supports.",
    ),
    "youtube.i18nRegions.list": (
        "Get content regions",
        "Reads the content regions YouTube supports.",
    ),
}

#: Method ids of the source that have no step, each with the reason.
EXCLUDED: dict[str, str] = {
    "youtube.tests.insert": (
        'The source documents it only as "POST method." with a TestItem body: it is not a '
        "described YouTube feature, so no step is offered for it."
    ),
    "youtube.youtube.v3.liveChat.messages.stream": (
        "A server-streamed RPC: the answer is a stream that stays open while the chat is "
        "live, which one workflow step cannot hold. Get live chat messages reads the same "
        "messages page by page."
    ),
}

#: Area -> the resources (second part of the method id) it holds, in page order.
AREAS: dict[str, list[str]] = {
    "Channels": [
        "channels",
        "channelSections",
        "channelBanners",
        "watermarks",
        "activities",
        "members",
        "membershipsLevels",
        "thirdPartyLinks",
    ],
    "Videos": [
        "videos",
        "videoTrainability",
        "thumbnails",
        "search",
        "videoCategories",
        "videoAbuseReportReasons",
        "abuseReports",
    ],
    "Playlists": ["playlists", "playlistItems", "playlistImages"],
    "Comments and captions": ["commentThreads", "comments", "captions"],
    "Live streaming": [
        "liveBroadcasts",
        "liveStreams",
        "liveChatMessages",
        "liveChatBans",
        "liveChatModerators",
        "superChatEvents",
    ],
    "Subscriptions and regions": ["subscriptions", "i18nLanguages", "i18nRegions"],
}

#: The verbs a step title may start with.
VERBS = {
    "Get",
    "Update",
    "Create",
    "Delete",
    "Upload",
    "Set",
    "Remove",
    "Rate",
    "Report",
    "Search",
    "Download",
    "Mark",
    "Bind",
    "Change",
    "Insert",
    "Send",
    "Ban",
    "Add",
    "Query",
    "Test",
    "List",
    "Reply",
    "Check",
}
