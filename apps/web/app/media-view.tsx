"use client";

import { useEffect, useState } from "react";
import { apiBase, notifySessionExpired } from "./api";

/** Fetch private media with the session header; never put bearer tokens in URLs. */
export default function MediaView({
  path,
  token,
  image = false,
  alt = "",
}: {
  path: string;
  token: string;
  image?: boolean;
  alt?: string;
}) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    setUrl("");
    setError("");
    void fetch(apiBase + path, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 401) notifySessionExpired(token);
        if (!response.ok)
          throw new Error(
            "Private media could not be loaded. Refresh your session and retry.",
          );
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setError(err instanceof Error ? err.message : "Media unavailable");
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path, token]);
  if (error)
    return (
      <p role="alert" className="error">
        {error}
      </p>
    );
  if (!url) return <p className="muted">Loading private media…</p>;
  // Samples are authenticated blobs, so Next's public image optimizer cannot fetch them.
  return image ? (
    <img src={url} alt={alt} className="sample-image" />
  ) : (
    <video
      src={url}
      controls
      playsInline
      preload="metadata"
      className="submission-video"
    />
  );
}
