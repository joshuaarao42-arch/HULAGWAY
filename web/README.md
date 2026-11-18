# Hulagway Web Edition

The Hulagway Web Edition is a browser-based companion to the original Python desktop application. It is maintained in this directory so the desktop code and workflow remain separate.

**Live application:** https://hulagway-joshy3.vercel.app

## Features

- Username-based registration and login.
- Secure password hashing and signed sessions.
- Image compression, format conversion, resizing, and optimization.
- Image inspection for dimensions, format, colour mode, transparency, and available metadata.
- Per-account processing history stored in Neon PostgreSQL.
- Batch processing for up to 8 images per request.
- ZIP downloads for batch results.
- Responsive interface for desktop and mobile.

## Technology

- Flask
- Pillow
- Neon PostgreSQL
- Vercel

## Configuration

The deployment expects these environment variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `SECRET_KEY` | Secret used to sign Flask sessions |

Set both variables in the hosting provider's environment settings. Do not put real credentials in this file, source code, screenshots, or Git history.

## Deployment notes

The Vercel project is connected to this GitHub repository and uses `web/` as its Root Directory. Changes pushed to the configured production branch trigger a deployment.

The web service currently accepts a maximum total upload size of 4 MB per request and up to 8 images in one batch. Keep these limits in mind when testing.

## Screenshots

Paste the direct image URLs into the three boxes below. Replace only `PASTE_IMAGE_LINK_HERE` in each image tag; the layout and captions are already set.

<table>
  <tr>
    <td align="center" width="33%">
      <strong>Image Studio</strong><br>
      <img src="PASTE_IMAGE_LINK_HERE" alt="Hulagway Image Studio" width="100%">
    </td>
    <td align="center" width="33%">
      <strong>Image Inspector</strong><br>
      <img src="PASTE_IMAGE_LINK_HERE" alt="Hulagway Image Inspector" width="100%">
    </td>
    <td align="center" width="33%">
      <strong>Processing History</strong><br>
      <img src="PASTE_IMAGE_LINK_HERE" alt="Hulagway Processing History" width="100%">
    </td>
  </tr>
</table>

## Desktop edition

The original CustomTkinter desktop application remains in the repository root. Its installation instructions and desktop feature documentation are in the [main README](../README.md).
