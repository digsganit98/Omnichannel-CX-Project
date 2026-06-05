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
    """Synthesize :Policy nodes from Claim_data (unique CustomerID + PolicyType combos)."""
    rows = _rows(wb, "Claim_data")
    seen: set[str] = set()
    count = 0
    for row in rows:
        customer_id = str(row.get("CustomerID", ""))
        policy_type = str(row.get("PolicyType") or "")
        claim_id = str(row.get("ClaimID", ""))
        if not customer_id or not policy_type:
            continue
        policy_id = f"{customer_id}_{policy_type.replace(' ', '_').upper()}"
        if policy_id not in seen:
            seen.add(policy_id)
            client.write(
                """
                MERGE (p:Policy {policy_id: $policy_id})
                SET p.policy_type = $policy_type,
                    p.customer_id = $customer_id,
                    p.status = 'Active'
                WITH p
                MATCH (c:Customer {customer_id: $customer_id})
                MERGE (c)-[:HAS_POLICY]->(p)
                """,
                {"policy_id": policy_id, "policy_type": policy_type, "customer_id": customer_id},
            )
            count += 1
        # Link Policy → Claim
        if claim_id:
            client.write(
                """
                MATCH (p:Policy {policy_id: $policy_id})
                MATCH (cl:Claim {claim_id: $claim_id})
                MERGE (p)-[:HAS_CLAIM]->(cl)
                """,
                {"policy_id": policy_id, "claim_id": claim_id},
            )
    return count


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
