"""Load bfsi.xlsx into Neo4j graph.

Sheets handled:
  Customer_data          → (:Customer) nodes
  Loan_Processing_data   → (:Loan) nodes + [:HAS_LOAN] edges
  Claim_data             → (:Claim) nodes + [:HAS_CLAIM] edges
  Loan_Policy_Product_data → (:Product) nodes
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


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    from services.neo4j_service.client import Neo4jClient
    client = Neo4jClient()
    result = load_bfsi_data(client)
    print("Loaded:", result)
    client.close()
