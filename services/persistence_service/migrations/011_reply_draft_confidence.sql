-- Store the confidence scores that were live when a reply was held for review, so the admin
-- reviewing the draft can see how strongly grounded the AI's answer was.
--   retrieval_confidence = top KB-match score (0..1) — explains "no knowledge found" holds
--   intent_confidence    = classifier certainty about the detected intent (0..1)
-- Nullable: legacy drafts predate the feature and simply won't show the pills.
ALTER TABLE reply_drafts ADD COLUMN retrieval_confidence REAL;
ALTER TABLE reply_drafts ADD COLUMN intent_confidence REAL;
