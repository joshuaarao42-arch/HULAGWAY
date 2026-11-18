# Hulagway Screenshot Template

Use this folder to keep the project's screenshots organized. The root [README](../../README.md) already displays the existing desktop screenshots. This template is for adding a consistent set of **six web edition screenshots**.

## Capture checklist

- Use the same browser zoom level for all screenshots (100% recommended).
- Capture the actual application UI; do not include browser tabs, personal information, passwords, tokens, or private account data.
- Use realistic sample images that you own or are allowed to use.
- Keep the window size consistent where possible.
- Prefer PNG screenshots at a readable resolution.
- Before committing, confirm each image is legible on both desktop and mobile-sized displays.

## Six-image web gallery

Save the six screenshots in this directory with these exact filenames, then uncomment or adapt the Markdown image links below.

| # | Filename | What to capture |
|---|---|---|
| 1 | `web-01-home.png` | Landing page or main workspace before processing |
| 2 | `web-02-signup-login.png` | Signup or login screen; use a test account and never show a real password |
| 3 | `web-03-compressor.png` | Image compression settings and selected sample image |
| 4 | `web-04-conversion-resize.png` | Format conversion or resize controls and output settings |
| 5 | `web-05-inspector.png` | Image inspector showing sample image details |
| 6 | `web-06-history-results.png` | Processing history and completed result/download state |

## Markdown gallery template

Copy this block into the Web Edition section of the root README after all six images have been added:

```markdown
### Web application

| Home workspace | Signup and login |
|---|---|
| ![Hulagway web home](docs/screenshots/web-01-home.png) | ![Hulagway signup and login](docs/screenshots/web-02-signup-login.png) |

| Image compressor | Conversion and resize |
|---|---|
| ![Hulagway web compressor](docs/screenshots/web-03-compressor.png) | ![Hulagway conversion and resize](docs/screenshots/web-04-conversion-resize.png) |

| Image inspector | History and results |
|---|---|
| ![Hulagway web inspector](docs/screenshots/web-05-inspector.png) | ![Hulagway web history and results](docs/screenshots/web-06-history-results.png) |
```

## Current status

The six image files are intentionally not included yet. Add the real screenshots after capturing the deployed web application; the template does not use fake or empty image assets.
