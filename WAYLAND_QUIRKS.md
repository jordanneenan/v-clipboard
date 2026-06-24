# Wayland Clipboard Quirks & Architecture

Building a reliable clipboard manager on Wayland (specifically GNOME/Mutter) poses several deeply technical challenges due to the security-first architecture of the protocol. This document outlines the major architectural hurdles encountered during the development of V Clipboard and the mitigation strategies implemented.

## 1. The Background App Isolation
By design, Wayland compositors isolate background applications from clipboard events to prevent keylogging and clipboard sniffing.
* **The Problem**: Native GTK clipboard event signals (e.g. `Gtk.Clipboard.get().connect("owner-change")`) silently fail to fire if the application window does not have active Wayland focus.
* **The Solution**: We are forced to actively poll the clipboard using the `wl-clipboard` utility via `subprocess`.

## 2. Polling Deadlocks & Non-Deterministic Types
Polling the clipboard several times a second introduces severe edge cases regarding how target apps respond.
* **The Problem**: Some apps provide a non-deterministic ordering of clipboard MIME types. e.g. `wl-paste --list-types` might return `image/png, text/plain` on one poll, and `text/plain, image/png` 500ms later. If a clipboard manager hashes these types to detect a state change, the changing order forces a cache miss, causing the clipboard manager to think a new item was copied.
* **The Solution**: The MIME types array MUST be strictly sorted alphabetically before hashing to guarantee deterministic state signatures.

## 3. Dynamic PNG Re-Encoding (The "Flashing" Loop)
When an application offers rich text or an image, it often advertises `image/png` as an available type.
* **The Problem**: Wayland dynamically generates and re-encodes the PNG from raw memory *every single time* it is requested. Because of timestamp/deflate variances in the real-time encoding, the output PNG file size slightly fluctuates by a few bytes on every request.
* **The Effect**: If the clipboard manager uses the image size or hash to determine if an image is "new", the fluctuating PNG size causes it to ingest the "new" image every polling cycle (twice a second).
* **The Glitch**: Ingesting an image triggers a system tray menu refresh (`AppIndicator`). Refreshing an `AppIndicator` twice a second forces the entire GNOME Shell top bar layout engine to rapidly redraw, which causes adjacent icons (like the Battery Charger indicator) to visually glitch and flicker on and off.
* **The Solution**: V Clipboard implements an aggressive size-tolerance threshold. If the incoming image's size differs by less than 50 bytes from the last known image, the engine identifies it as a dynamic re-encode of the same graphic and safely drops the update, halting the infinite UI spam loop.

## 4. Unreliable Primary Keys
Some browser extensions and password managers dynamically inject tracking tokens or one-time hashes into the rich text representation of the clipboard (`text/html`), causing the actual text payload to change slightly on subsequent reads.
* **The Solution**: V Clipboard employs a hard circuit breaker: before any UI update is dispatched, the incoming payload is compared mathematically to the item residing at index `0` of the history array. If they match semantically, the entire update chain is aborted.
