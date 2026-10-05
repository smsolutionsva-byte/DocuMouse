# DocuMouse web

The Next.js (App Router) + TypeScript + Tailwind CSS frontend. See the
[project README](../README.md) for setup.

```bash
npm install
npm run dev        # http://localhost:3000, proxies /api to DOCUMOUSE_API_URL
npm run lint
npm run typecheck
```

Where things live:

| Path | What |
| --- | --- |
| `src/app/globals.css` | Design tokens (colour, type, radii, shadows, motion) |
| `src/components/ui/` | Small shared primitives: Button, Dialog, Menu, Toast, Mouse |
| `src/components/review/` | The review screen: viewer, fields, table editor, assistant, history, export |
| `src/components/upload/` | Drop zone and live processing queue |
| `src/components/documents/` | Library list and filters |
| `src/lib/` | API client, types, formatting |
