#!/usr/bin/env bash
set -euo pipefail

# Keep generated pages/data separate from source and preserve newer commits on main.
git config user.name "acq-bot"
git config user.email "acq-bot@users.noreply.github.com"
git add -A -- index.html sport.html hot.html news.html music.html arhiva.html arhiva scripts/data sitemap.xml robots.txt llms.txt

if git diff --cached --quiet; then
  echo "Nu sunt modificări de salvat. Sincronizez main înainte de publicare."
else
  edition_date="$(TZ=Europe/Bucharest date +%F)"
  git commit -m "${1:-Ediția} ${edition_date}"
fi

# Retry Git synchronization only. Never regenerate the edition or call Gemini here.
for attempt in 1 2 3; do
  git fetch --no-tags origin main
  if ! git rebase origin/main; then
    git rebase --abort || true
    echo "::error::O modificare concurentă se suprapune cu ediția. Nu suprascriu modificările din main."
    exit 1
  fi
  if git push origin HEAD:main; then
    echo "Ediția și codul sunt sincronizate cu main."
    exit 0
  fi
  echo "main a fost actualizat în timpul salvării; repet sincronizarea Git (${attempt}/3)."
done

echo "::error::Nu am putut salva ediția după trei sincronizări Git."
exit 1
