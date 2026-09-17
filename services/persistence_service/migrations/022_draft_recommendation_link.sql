-- Which recommendation produced this draft, so discarding the draft can undo the approve.
--
-- Approving a Suggested Action or a Suggested Offer flips the recommendation to `approved`
-- and creates a draft. Discarding that draft only touched the draft: the recommendation
-- stayed `approved`, so the card stopped offering it while nothing had been sent and the
-- agent had never pressed Dismiss. The work was neither done nor available - two rows were
-- already stuck that way when this was written (one cross_sell, one information_needed).
--
-- NULL for a pipeline-held draft. Those come from the review gate, not from a
-- recommendation, and there is nothing to revert when one is discarded.
ALTER TABLE reply_drafts ADD COLUMN recommendation_id TEXT;

CREATE INDEX IF NOT EXISTS idx_reply_drafts_recommendation
    ON reply_drafts(recommendation_id);
