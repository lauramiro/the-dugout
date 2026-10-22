"use client";

import { useCallback, useMemo, useState } from "react";
import type { Vote } from "./calls";
import { LocalVotes, ServiceVotes, type VoteStore } from "./votes";

/** "Your call" votes for one page: replay votes stay in the page; live votes also go to the
 *  service, which answers with the crowd tally. The first call on a card stands. */
export function useVotes(live: boolean): {
  votes: Record<string, Vote>;
  castVote: (id: string, option: string | null) => void;
  /** Forget this page's calls (a fresh run of the story). */
  reset: () => void;
} {
  const voteStore = useMemo<VoteStore>(() => (live ? new ServiceVotes() : new LocalVotes()), [live]);
  const [votes, setVotes] = useState<Record<string, Vote>>({});
  const castVote = useCallback(
    (id: string, option: string | null) => {
      setVotes((v) => (id in v ? v : { ...v, [id]: { option, tally: null, error: null } }));
      if (option === null) return;
      voteStore.cast(id, option).then(
        (tally) => setVotes((v) => ({ ...v, [id]: { ...v[id], tally } })),
        (err: unknown) => setVotes((v) => ({ ...v, [id]: { ...v[id], error: err instanceof Error ? err.message : String(err) } })),
      );
    },
    [voteStore],
  );
  const reset = useCallback(() => setVotes({}), []);
  return { votes, castVote, reset };
}
