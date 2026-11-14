# SwarmMemory dashboard

The Next.js frontend for SwarmMemory. It shows the agent swarm, the memory explorer, verification, the marketplace, the network economy and every contract call, polling the API live. See the [root README](../README.md) for the full project.

## Run

```bash
cp .env.example .env.local     # NEXT_PUBLIC_API_URL, NEAR network and contract settings
npm install
npm run dev                    # http://localhost:3000
```

The backend must be running (`./scripts/run_backend.sh demo` from the repo root). The API only accepts requests from the origins in `CORS_ORIGINS` (default `http://localhost:3000`).

```bash
npm run lint
npm run build && npm start     # production build
```

## Structure

| Path | What |
|---|---|
| `src/app/` | One folder per page: overview, agents, memories, verification, marketplace, economy, transactions, activity |
| `src/components/app-shell.tsx` | Sidebar, top bar, mobile menu, page header |
| `src/components/bits.tsx` | Shared pieces: status pills, agent avatars, stat tiles, confidence meter, tx hashes |
| `src/components/scenario-runner.tsx` | The end-to-end demo runner on the overview page |
| `src/components/memory-dialog.tsx` | Memory Capsule detail: claim, evidence, verifications, ledger, wallet purchase |
| `src/components/swarm-diagram.tsx` | Hero illustration |
| `src/lib/api.ts`, `src/lib/hooks.ts` | API types, fetcher, and live-polling SWR hooks |
| `src/lib/wallet.tsx` | NEAR Wallet Selector (MyNearWallet, Meteor). Enabled in testnet mode only |
| `src/app/globals.css` | Design tokens for the light and dark themes |

## Design

- Warm "ivory paper" light theme (default) and a warm charcoal dark theme, toggled from the top bar.
- One accent colour (ember). Semantic colours: green for verified and confirmed, red for disputed and failed, amber for pending, violet for on-chain.
- Bricolage Grotesque for headings, Geist for text, Geist Mono for hashes and amounts.
- Every colour is a CSS variable in `globals.css`, so components never hard-code a theme.
