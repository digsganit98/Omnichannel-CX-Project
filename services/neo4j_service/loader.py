"""Load bfsi.xlsx into Neo4j graph.

Sheets handled:
  Customer_data          → (:Customer) nodes + (:KYC) nodes
  Loan_Processing_data   → (:Loan) nodes + [:HAS_LOAN] edges + [:PRODUCT_IS] links
  Claim_data             → (:Claim) nodes + (:Policy) nodes + [:HAS_CLAIM] / [:HAS_POLICY] edges
  Loan_Policy_Product_data → (:Product) nodes
Runtime:
  (:Agent) nodes for AI and human handlers (always created)
"""

from pathlib import Path
import logging
import openpyxl

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BFSI_XLSX = ROOT / "data" / "bfsi.xlsx"


def load_bfsi_data(client) -> dict:
    wb = openpyxl.load_workbook(BFSI_XLSX)
    counts: dict[str, int] = {}

    counts["customers"] = _load_customers(client, wb)
    counts["loans"] = _load_loans(client, wb)
    counts["loan_schedules"] = _load_loan_schedules(client, wb)
    counts["loan_collateral"] = _load_loan_collateral(client, wb)
    counts["claims"] = _load_claims(client, wb)
    counts["products"] = _load_products(client, wb)
    counts["policies"] = _load_policies(client, wb)
    counts["kyc"] = _load_kyc(client, wb)
    counts["product_links"] = _load_product_links(client, wb)
    counts["agents"] = _load_agents(client)

    logger.info("bfsi_data_loaded", extra=counts)
    return counts


def _rows(wb, sheet: str) -> list[dict]:
    if sheet not in wb.sheetnames:
        return []
    ws = wb[sheet]
    headers = [cell.value for cell in next(ws.iter_rows(max_row=1))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if any(v is not None for v in row):
            rows.append(dict(zip(headers, row)))
    return rows


def _load_customers(client, wb) -> int:
    rows = _rows(wb, "Customer_data")
    for row in rows:
        client.write(
            """
            MERGE (c:Customer {customer_id: $customer_id})
            SET c.email = $email,
                c.secondary_email = $secondary_email,
                c.phone = $phone,
                c.city = $city,
                c.country = $country,
                c.registration_date = $registration_date,
                c.last_activity_date = $last_activity_date
            """,
            {
                "customer_id": str(row.get("CustomerID", "")),
                "email": str(row.get("PrimaryEmail") or ""),
                "secondary_email": str(row.get("SecondaryEmail") or ""),
                "phone": str(row.get("Phone") or ""),
                "city": str(row.get("City") or ""),
                "country": str(row.get("Country") or ""),
                "registration_date": str(row.get("RegistrationDate") or ""),
                "last_activity_date": str(row.get("LastActivityDate") or ""),
            },
        )
    return len(rows)


def _load_loans(client, wb) -> int:
    rows = _rows(wb, "Loan_Processing_data")
    for row in rows:
        customer_id = str(row.get("CustomerID", ""))
        loan_id = str(row.get("LoanID", ""))
        client.write(
            """
            MERGE (l:Loan {loan_id: $loan_id})
            SET l.loan_type = $loan_type,
                l.application_date = $application_date,
                l.status = $status,
                l.last_updated = $last_updated,
                l.amount_inr = $amount_inr,
                l.interest_rate = $interest_rate,
                l.next_step = $next_step
            WITH l
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_LOAN]->(l)
            """,
            {
                "loan_id": loan_id,
                "customer_id": customer_id,
                "loan_type": str(row.get("LoanType") or ""),
                "application_date": str(row.get("ApplicationDate") or ""),
                "status": str(row.get("LoanStatus") or ""),
                "last_updated": str(row.get("LastUpdatedDate") or ""),
                "amount_inr": row.get("LoanAmount (INR)") or 0,
                "interest_rate": row.get("InterestRate (%)") or 0,
                "next_step": str(row.get("NextStep") or ""),
            },
        )
    return len(rows)


def _load_loan_schedules(client, wb) -> int:
    """Set summary loan-servicing properties on existing :Loan nodes (items 15 & 16).

    Reads Loan_Schedule_data, which contains ONLY disbursed loans (a non-disbursed
    loan has no EMI obligation and therefore no schedule and no arrears — it simply
    has no row here, and the answer layer's `if loan.get('emi_amount_inr')` /
    `if dpd > 0` guards handle the absent properties gracefully). For each row we set
    both the EMI-schedule fields (item 15) and the arrears/DPD fields (item 16).
    """
    rows = _rows(wb, "Loan_Schedule_data")
    applied = 0
    for row in rows:
        loan_id = str(row.get("LoanID") or "")
        if not loan_id:
            continue
        client.write(
            """
            MATCH (l:Loan {loan_id: $loan_id})
            SET l.tenure_months            = $tenure_months,
                l.emis_paid                = $emis_paid,
                l.emi_amount_inr           = $emi_amount_inr,
                l.outstanding_principal_inr = $outstanding_principal_inr,
                l.next_emi_date            = $next_emi_date,
                l.foreclosure_amount_inr   = $foreclosure_amount_inr,
                l.dpd                      = $dpd,
                l.overdue_amount_inr       = $overdue_amount_inr,
                l.penalty_inr              = $penalty_inr,
                l.arrears_bucket           = $arrears_bucket,
                l.collections_stage        = $collections_stage
            """,
            {
                "loan_id": loan_id,
                "tenure_months": row.get("TenureMonths") or 0,
                "emis_paid": row.get("EMIs_Paid") or 0,
                "emi_amount_inr": row.get("EMI_Amount_INR") or 0,
                "outstanding_principal_inr": row.get("Outstanding_Principal_INR") or 0,
                "next_emi_date": str(row.get("Next_EMI_Date") or ""),
                "foreclosure_amount_inr": row.get("Foreclosure_Amount_INR") or 0,
                "dpd": row.get("DPD") or 0,
                "overdue_amount_inr": row.get("Overdue_Amount_INR") or 0,
                "penalty_inr": row.get("Penalty_INR") or 0,
                "arrears_bucket": str(row.get("Bucket") or "Current"),
                "collections_stage": str(row.get("Collections_Stage") or "None"),
            },
        )
        applied += 1
    return applied


def _load_loan_collateral(client, wb) -> int:
    """Set collateral + disbursement props on existing :Loan nodes (item 17).

    Reads Loan_Collateral_data. Secured loans get collateral_type / collateral_value_inr
    / ltv_percent; all loans get sanctioned_amount_inr / disbursed_amount_inr. Unsecured
    loans (Personal/Education) carry no collateral fields — the answer layer's
    `if loan.get('collateral_type')` guard skips them.
    """
    rows = _rows(wb, "Loan_Collateral_data")
    for row in rows:
        loan_id = str(row.get("LoanID") or "")
        if not loan_id:
            continue
        secured = str(row.get("Secured") or "").strip().lower() == "yes"
        client.write(
            """
            MATCH (l:Loan {loan_id: $loan_id})
            SET l.sanctioned_amount_inr = $sanctioned,
                l.disbursed_amount_inr  = $disbursed,
                l.collateral_type       = $collateral_type,
                l.collateral_value_inr  = $collateral_value,
                l.ltv_percent           = $ltv
            """,
            {
                "loan_id": loan_id,
                "sanctioned": row.get("Sanctioned_Amount_INR") or 0,
                "disbursed": row.get("Disbursed_Amount_INR") or 0,
                # Secured-only fields; unsecured loans store empty/0 so guards skip them.
                "collateral_type": str(row.get("Collateral_Type") or "") if secured else "",
                "collateral_value": (row.get("Collateral_Value_INR") or 0) if secured else 0,
                "ltv": (row.get("LTV_Percent") or 0) if secured else 0,
            },
        )
    return len(rows)


def _load_claims(client, wb) -> int:
    rows = _rows(wb, "Claim_data")
    for row in rows:
        customer_id = str(row.get("CustomerID", ""))
        claim_id = str(row.get("ClaimID", ""))
        client.write(
            """
            MERGE (cl:Claim {claim_id: $claim_id})
            SET cl.policy_type = $policy_type,
                cl.claim_type = $claim_type,
                cl.status = $status,
                cl.last_updated = $last_updated,
                cl.amount_claimed_inr = $amount_claimed,
                cl.amount_approved_inr = $amount_approved,
                cl.reason = $reason
            WITH cl
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_CLAIM]->(cl)
            """,
            {
                "claim_id": claim_id,
                "customer_id": customer_id,
                "policy_type": str(row.get("PolicyType") or ""),
                "claim_type": str(row.get("ClaimType") or ""),
                "status": str(row.get("ClaimStatus") or ""),
                "last_updated": str(row.get("LastUpdatedDate") or ""),
                "amount_claimed": row.get("AmountClaimed (INR)") or 0,
                "amount_approved": row.get("AmountApproved (INR)") or 0,
                "reason": str(row.get("ReasonForStatus") or ""),
            },
        )
    return len(rows)


def _load_products(client, wb) -> int:
    rows = _rows(wb, "Loan_Policy_Product_data")
    for row in rows:
        client.write(
            """
            MERGE (p:Product {product_id: $product_id})
            SET p.name = $name,
                p.product_type = $product_type,
                p.category = $category,
                p.description = $description,
                p.key_features = $key_features,
                p.eligibility = $eligibility
            """,
            {
                "product_id": str(row.get("ProductID") or ""),
                "name": str(row.get("ProductName") or ""),
                "product_type": str(row.get("ProductType") or ""),
                "category": str(row.get("Category") or ""),
                "description": str(row.get("Description") or ""),
                "key_features": str(row.get("KeyFeatures") or ""),
                "eligibility": str(row.get("EligibilityCriteria") or ""),
            },
        )
    return len(rows)


def _load_policies(client, wb) -> int:
    """Load per-customer :Policy nodes from the Customer_Policy_data sheet.

    This is the customer-held policy instance data (distinct from the
    Loan_Policy_Product_data product catalogue). It sets the real financial
    fields that get_policy_status() queries — premium_inr, coverage_inr,
    maturity_date, next_premium_due — which the old claim-synthesized stub
    never populated (they always returned null).

    Policies are linked to their matching catalogue :Product by policy_type,
    and to the customer's existing :Claim nodes by (customer + policy_type),
    preserving the prior Policy->Claim relationship.
    """
    rows = _rows(wb, "Customer_Policy_data")
    for row in rows:
        customer_id = str(row.get("CustomerID") or "")
        policy_id = str(row.get("PolicyID") or "")
        policy_type = str(row.get("PolicyType") or "")
        if not customer_id or not policy_id:
            continue
        maturity = str(row.get("MaturityDate") or "")
        # Treat the "annual renewal" sentinel as no maturity date so the query's
        # `if p.get('maturity_date')` guard skips it cleanly.
        if maturity.upper().startswith("N/A"):
            maturity = ""
        client.write(
            """
            MERGE (p:Policy {policy_id: $policy_id})
            SET p.customer_id      = $customer_id,
                p.policy_type      = $policy_type,
                p.policy_number    = $policy_number,
                p.coverage_inr     = $coverage_inr,
                p.premium_inr      = $premium_inr,
                p.premium_frequency = $premium_frequency,
                p.premium_paid_to  = $premium_paid_to,
                p.next_premium_due = $next_premium_due,
                p.maturity_date    = $maturity_date,
                p.status           = $status,
                p.premiums_paid       = $premiums_paid,
                p.last_premium_date   = $last_premium_date,
                p.premium_status      = $premium_status,
                p.overdue_premium_inr = $overdue_premium_inr,
                p.late_fee_inr        = $late_fee_inr,
                p.grace_period_days   = $grace_period_days
            WITH p
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_POLICY]->(p)
            """,
            {
                "policy_id": policy_id,
                "customer_id": customer_id,
                "policy_type": policy_type,
                "policy_number": str(row.get("PolicyNumber") or ""),
                "coverage_inr": row.get("SumAssured_INR") or 0,
                "premium_inr": row.get("PremiumAmount_INR") or 0,
                "premium_frequency": str(row.get("PremiumFrequency") or ""),
                "premium_paid_to": str(row.get("PremiumPaidTo") or ""),
                "next_premium_due": str(row.get("NextPremiumDue") or ""),
                "maturity_date": maturity,
                "status": str(row.get("Status") or "Active"),
                # Item 12: premium payment history (derived consistent with status).
                "premiums_paid": row.get("Premiums_Paid") or 0,
                "last_premium_date": str(row.get("Last_Premium_Date") or ""),
                "premium_status": str(row.get("Premium_Status") or "Paid"),
                "overdue_premium_inr": row.get("Overdue_Premium_INR") or 0,
                "late_fee_inr": row.get("Late_Fee_INR") or 0,
                "grace_period_days": row.get("Grace_Period_Days") or 0,
            },
        )
        # Link Policy -> matching catalogue Product by policy_type (best-effort).
        if policy_type:
            client.write(
                """
                MATCH (p:Policy {policy_id: $policy_id})
                MATCH (prod:Product)
                WHERE prod.product_type = 'Policy'
                  AND (prod.category CONTAINS $policy_type OR $policy_type CONTAINS prod.category)
                MERGE (p)-[:PRODUCT_IS]->(prod)
                """,
                {"policy_id": policy_id, "policy_type": policy_type},
            )
        # Preserve Policy -> Claim links: attach this customer's claims of the same type.
        client.write(
            """
            MATCH (c:Customer {customer_id: $customer_id})-[:HAS_CLAIM]->(cl:Claim)
            WHERE cl.policy_type = $policy_type
            MATCH (p:Policy {policy_id: $policy_id})
            MERGE (p)-[:HAS_CLAIM]->(cl)
            """,
            {"customer_id": customer_id, "policy_id": policy_id, "policy_type": policy_type},
        )
    return len(rows)


def _load_kyc(client, wb) -> int:
    """Create one :KYC node per customer (stub with Pending status)."""
    rows = _rows(wb, "Customer_data")
    for row in rows:
        customer_id = str(row.get("CustomerID", ""))
        if not customer_id:
            continue
        client.write(
            """
            MERGE (k:KYC {customer_id: $customer_id})
            SET k.kyc_status   = 'Pending',
                k.registered_at = $registered_at
            WITH k
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:KYC_VERIFIED_BY]->(k)
            """,
            {
                "customer_id": customer_id,
                "registered_at": str(row.get("RegistrationDate") or ""),
            },
        )
    return len(rows)


def _load_product_links(client, wb) -> int:
    """Link Loan nodes to Product nodes via [:PRODUCT_IS] by matching loan_type."""
    rows = _rows(wb, "Loan_Processing_data")
    count = 0
    for row in rows:
        loan_id = str(row.get("LoanID", ""))
        loan_type = str(row.get("LoanType") or "")
        if not loan_id or not loan_type:
            continue
        client.write(
            """
            MATCH (l:Loan {loan_id: $loan_id})
            MATCH (p:Product)
            WHERE p.product_type = $loan_type
               OR p.name CONTAINS $loan_type
               OR p.category = $loan_type
            MERGE (l)-[:PRODUCT_IS]->(p)
            """,
            {"loan_id": loan_id, "loan_type": loan_type},
        )
        count += 1
    return count


def _load_agents(client) -> int:
    """Create default Agent nodes for AI handler and stub human handler."""
    agents = [
        {
            "agent_id": "AI_GROQ",
            "agent_type": "ai",
            "name": "InboxIQ AI",
            "model": "llama-3.1-8b-instant",
        },
        {
            "agent_id": "HUMAN_SR",
            "agent_type": "human",
            "name": "Support Representative",
            "model": "",
        },
    ]
    for agent in agents:
        client.write(
            """
            MERGE (a:Agent {agent_id: $agent_id})
            SET a.agent_type = $agent_type,
                a.name       = $name,
                a.model      = $model
            """,
            agent,
        )
    return len(agents)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    from services.neo4j_service.client import Neo4jClient
    client = Neo4jClient()
    result = load_bfsi_data(client)
    print("Loaded:", result)
    client.close()
