-- Offer drafts (channel='offer') carry the cross-sell/up-sell PRODUCT id
-- (e.g. health_insurance, credit_card, fd_renewal) captured from the originating
-- opportunity recommendation at approve time. The conversation view maps this
-- product to an intent/theme so the offer groups with the matching topic group
-- (or forms its own themed group), instead of gluing under the unrelated query
-- that merely preceded it. Nullable: legacy offer drafts + all non-offer drafts
-- have no product.
ALTER TABLE reply_drafts ADD COLUMN offer_product TEXT;
